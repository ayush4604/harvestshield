"""Classical ML with exact calendar labels and globally chronological evaluation."""
from datetime import datetime, timezone
import json
import threading

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, mean_absolute_error, mean_squared_error, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from .config import today_ist
from .config import Settings
from .data import IDENTITY, ProjectError, Store

HORIZON = 7
DROP_THRESHOLD = 0.15
MAX_AGE_DAYS = 3
FEATURES = ["price", "lag1", "lag3", "lag7", "lag1_age", "lag7_age", "mean7", "mean14", "std14", "return1", "return7", "count14", "month_sin", "month_cos", "weekday"]
MODEL_VERSION = 1


def make_features(frame):
    chunks = []
    for sid, group in frame.groupby("series_id", sort=False):
        group = group.sort_values("date").copy()
        dates = pd.to_datetime(group.date)
        price = pd.Series(group.modal_price.to_numpy(float), index=pd.DatetimeIndex(dates))
        out = pd.DataFrame({"series_id": sid, "date": dates.to_numpy(), "price": price.to_numpy()})
        for lag in (1, 3, 7):
            out[f"lag{lag}"] = price.shift(lag).to_numpy()
        out["lag1_age"] = dates.diff().dt.days.to_numpy()
        out["lag7_age"] = (dates - dates.shift(7)).dt.days.to_numpy()
        out["mean7"] = price.rolling("7D").mean().to_numpy()
        out["mean14"] = price.rolling("14D").mean().to_numpy()
        out["std14"] = price.rolling("14D").std().to_numpy()
        out["count14"] = price.rolling("14D").count().to_numpy()
        out["return1"] = out.price / out.lag1 - 1
        out["return7"] = out.price / out.lag7 - 1
        out["month_sin"] = np.sin(2 * np.pi * pd.DatetimeIndex(out.date).month / 12)
        out["month_cos"] = np.cos(2 * np.pi * pd.DatetimeIndex(out.date).month / 12)
        out["weekday"] = pd.DatetimeIndex(out.date).dayofweek
        lookup = price.to_dict()
        out["target_date"] = out.date + pd.Timedelta(days=HORIZON)
        out["target_price"] = out.target_date.map(lookup)
        out["drop_event"] = np.where(out.target_price.notna(), (out.target_price <= out.price * (1 - DROP_THRESHOLD)).astype(float), np.nan)
        out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
        out = out[out.count14 >= 5]
        chunks.append(out)
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def temporal_split(rows):
    labeled = rows.dropna(subset=["target_price", "drop_event"]).copy()
    dates = sorted(labeled.date.unique())
    if len(dates) < 120:
        raise ProjectError("Need at least 120 distinct labeled dates. Import more historical observations.")
    val_start = pd.Timestamp(dates[int(len(dates) * 0.65)])
    test_start = pd.Timestamp(dates[int(len(dates) * 0.82)])
    train = labeled[(labeled.date < val_start) & (labeled.target_date < val_start)]
    val = labeled[(labeled.date >= val_start) & (labeled.date < test_start) & (labeled.target_date < test_start)]
    test = labeled[labeled.date >= test_start]
    if min(len(train), len(val), len(test)) < 30 or len(train) < 100:
        raise ProjectError("Insufficient usable records after chronological splits and seven-day gaps.")
    return train, val, test


def pipeline(estimator):
    prep = ColumnTransformer([
        ("numeric", StandardScaler(), FEATURES),
        ("market", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["series_id"]),
    ])
    return Pipeline([("features", prep), ("model", estimator)])


def positive_probability(model, x):
    probabilities = model.predict_proba(x)
    classes = list(model.classes_)
    return probabilities[:, classes.index(1)] if 1 in classes else np.zeros(len(x))


def probability_features(p):
    p = np.clip(p, 1e-5, 1 - 1e-5)
    return np.log(p / (1 - p)).reshape(-1, 1)


def regression_metrics(y, pred):
    return {"mae": float(mean_absolute_error(y, pred)),
            "rmse": float(np.sqrt(mean_squared_error(y, pred))),
            "wape": float(np.sum(np.abs(np.asarray(y) - pred)) / np.sum(np.abs(y)))}


def risk_metrics(y, p, threshold):
    y = np.asarray(y).astype(int)
    predicted = p >= threshold
    bins = []
    for lo, hi in zip(np.arange(0, 1, 0.2), np.arange(0.2, 1.2, 0.2)):
        mask = (p >= lo) & ((p < hi) if hi < 0.999 else (p <= 1))
        if mask.any():
            bins.append({"predicted_probability": float(np.mean(p[mask])), "observed_frequency": float(np.mean(y[mask])), "rows": int(mask.sum())})
    return {"precision": float(precision_score(y, predicted, zero_division=0)),
            "recall": float(recall_score(y, predicted, zero_division=0)),
            "f1": float(f1_score(y, predicted, zero_division=0)),
            "brier": float(brier_score_loss(y, p)),
            "average_precision": float(average_precision_score(y, p)) if len(np.unique(y)) == 2 else None,
            "events": int(y.sum()), "rows": len(y), "base_rate": float(y.mean()),
            "reliability_bins": bins}


class ModelService:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.Lock()

    def paths(self, mode):
        if mode not in ("demo", "real"):
            raise ProjectError("Unknown dataset mode.")
        root = self.store.settings.artifacts_dir / mode
        root.mkdir(parents=True, exist_ok=True)
        return root / "model.joblib", root / "evaluation.json"

    def training_frame(self, mode, series_ids=None):
        raw = self.store.frame(mode)
        if raw.empty:
            raise ProjectError("No observations available. Import historical data or load the demo first.")
        available = set(raw.series_id)
        if series_ids is not None:
            if not series_ids or len(series_ids) > 20 or len(set(series_ids)) != len(series_ids):
                raise ProjectError("Select between 1 and 20 distinct produce/market series.")
            if not set(series_ids).issubset(available):
                raise ProjectError("Selected training series is not present in this dataset.")
            selected = set(series_ids)
        else:
            # Daily snapshots must not silently change the evaluated historical cohort.
            selected = set()
            for sid, group in raw.groupby("series_id"):
                dates = set(pd.to_datetime(group.date))
                if sum(d + pd.Timedelta(days=HORIZON) in dates for d in dates) >= 120:
                    selected.add(sid)
            if not selected:
                raise ProjectError("No series has 120 exact seven-day labels. Import sufficient history before training.")
        if len(selected) > 20:
            raise ProjectError("Select a focused cohort of at most 20 series before training.")
        return raw[raw.series_id.isin(selected)].copy(), sorted(available - selected)

    def train(self, mode, series_ids=None):
        if not self.lock.acquire(blocking=False):
            raise ProjectError("Another training job is running. Try again after it completes.", 409)
        try:
            with threadpool_limits(limits=2):
                return self._train(mode, series_ids)
        finally:
            self.lock.release()

    def _train(self, mode, series_ids=None):
        raw, excluded = self.training_frame(mode, series_ids)
        rows = make_features(raw)
        if rows.empty:
            raise ProjectError("Not enough history to generate features.")
        train, val, test = temporal_split(rows)
        xcols = FEATURES + ["series_id"]
        regressors = {
            "Ridge": Ridge(alpha=10),
            "Random Forest": RandomForestRegressor(n_estimators=100, min_samples_leaf=8, max_depth=12, random_state=42, n_jobs=2),
            "Gradient Boosting": HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=15, l2_regularization=2, random_state=42),
        }
        regression_models, comparisons = {}, []
        comparisons.append({"model": "Persistence baseline", **regression_metrics(val.target_price, val.price.to_numpy())})
        for name, estimator in regressors.items():
            fitted = pipeline(estimator).fit(train[xcols], train.target_price)
            regression_models[name] = fitted
            comparisons.append({"model": name, **regression_metrics(val.target_price, fitted.predict(val[xcols]))})
        reg_name = min(comparisons, key=lambda item: item["mae"])["model"]
        reg = regression_models.get(reg_name)
        def predict_reg(part):
            return np.maximum(1, reg.predict(part[xcols]) if reg is not None else part.price.to_numpy())

        ytrain = train.drop_event.astype(int)
        classifiers = {"Constant-risk baseline": DummyClassifier(strategy="prior")}
        if ytrain.nunique() == 2:
            classifiers.update({
                "Logistic Regression": LogisticRegression(max_iter=700, C=0.5, random_state=42),
                "Random Forest": RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=10, random_state=42, n_jobs=2),
                "Gradient Boosting": HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=10, l2_regularization=3, random_state=42),
            })
        risk_models, risk_comparisons = {}, []
        for name, estimator in classifiers.items():
            fitted = pipeline(estimator).fit(train[xcols], ytrain)
            risk_models[name] = fitted
            prob = positive_probability(fitted, val[xcols])
            risk_comparisons.append({"model": name, "brier": float(brier_score_loss(val.drop_event, prob))})
        risk_name = min(risk_comparisons, key=lambda item: item["brier"])["model"]
        risk_model = risk_models[risk_name]
        val_prob = positive_probability(risk_model, val[xcols])
        calibration = None
        # Calibration learns only from validation data; final test remains untouched.
        counts = val.drop_event.value_counts()
        if len(counts) == 2 and counts.min() >= 20 and np.std(val_prob) > 1e-6:
            calibration = LogisticRegression(C=10, random_state=42).fit(probability_features(val_prob), val.drop_event.astype(int))
            val_prob = calibration.predict_proba(probability_features(val_prob))[:, 1]
        alert_threshold = 0.30  # Fixed before viewing test performance.
        val_residual = val.target_price.to_numpy() - predict_reg(val)
        qlo, qhi = [float(v) for v in np.quantile(val_residual, [0.1, 0.9])]
        pred = predict_reg(test)
        test_prob = positive_probability(risk_model, test[xcols])
        if calibration is not None:
            test_prob = calibration.predict_proba(probability_features(test_prob))[:, 1]
        lower, upper = np.maximum(1, pred + qlo), np.maximum(1, pred + qhi)
        test_reg = regression_metrics(test.target_price, pred)
        baseline = regression_metrics(test.target_price, test.price.to_numpy())
        baseline_risk = risk_metrics(test.drop_event, np.full(len(test), float(ytrain.mean())), alert_threshold)
        test_risk = risk_metrics(test.drop_event, test_prob, alert_threshold)
        skill = 1 - test_reg["mae"] / baseline["mae"] if baseline["mae"] else None
        metadata = []
        for sid, group in raw.groupby("series_id"):
            last = group.iloc[-1]
            if sid in set(train.series_id):
                metadata.append({"series_id": sid, **{c: str(last[c]) for c in IDENTITY}})
        split_info = {}
        for name, part in (("train", train), ("validation", val), ("test", test)):
            split_info[name] = {"rows": len(part), "start": part.date.min().strftime("%Y-%m-%d"),
                "end": part.date.max().strftime("%Y-%m-%d"), "latest_target": part.target_date.max().strftime("%Y-%m-%d"),
                "drop_events": int(part.drop_event.sum())}
        warnings = []
        if mode == "demo":
            warnings.append("SYNTHETIC DEMO: all data and metrics are fictional demonstrations, not evidence of market forecasting quality.")
        if ytrain.nunique() < 2:
            warnings.append("Training contains only one risk class; the risk model is a constant baseline.")
        if calibration is None:
            warnings.append("Too few validation events or insufficient variation for calibration. Risk estimates are uncalibrated.")
        if int(test.drop_event.sum()) < 20:
            warnings.append("Fewer than 20 price-drop events in test; warning-performance estimates are unstable.")
        if skill is not None and skill <= 0:
            warnings.append("Selected forecast does not outperform persistence on the held-out test. Do not claim decision improvement.")
        if test_risk["brier"] >= baseline_risk["brier"]:
            warnings.append("Risk probabilities do not outperform the constant-frequency baseline on held-out test. Treat alerts as experimental, not validated decision support.")
        report = {
            "mode": mode, "synthetic": mode == "demo", "model_version": MODEL_VERSION,
            "trained_at": datetime.now(timezone.utc).isoformat(), "data_last_date": raw.date.max(),
            "data_rows": len(raw), "horizon_days": HORIZON, "drop_threshold": DROP_THRESHOLD,
            "training_series_ids": sorted(raw.series_id.unique()), "excluded_series_ids": excluded,
            "alert_probability_threshold": alert_threshold, "calibration": "validation sigmoid" if calibration is not None else "uncalibrated",
            "selected_regressor": reg_name, "selected_classifier": risk_name,
            "validation_regressors": comparisons, "validation_classifiers": risk_comparisons,
            "splits": split_info, "test_regression": test_reg, "test_persistence": baseline,
            "test_mae_skill": skill, "test_risk": test_risk, "test_risk_baseline": baseline_risk,
            "test_interval_coverage": float(np.mean((test.target_price >= lower) & (test.target_price <= upper))),
            "interval_note": "Approximate 80% interval from pooled validation residuals; no conditional coverage guarantee.",
            "per_market": [], "warnings": warnings,
        }
        for sid, group in test.groupby("series_id"):
            mask = test.series_id.eq(sid).to_numpy()
            market = raw[raw.series_id == sid].iloc[-1].market
            report["per_market"].append({"series_id": sid, "market": market, "rows": len(group), **regression_metrics(group.target_price, pred[mask])})
        bundle = {"version": MODEL_VERSION, "regressor": reg, "classifier": risk_model,
            "calibration": calibration, "residual_quantiles": (qlo, qhi), "series": metadata, "report": report}
        model_path, report_path = self.paths(mode)
        temp = model_path.with_suffix(".tmp")
        joblib.dump(bundle, temp)
        temp.replace(model_path)
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        return report

    def bundle(self, mode):
        path, _ = self.paths(mode)
        if not path.exists():
            raise ProjectError("No trained model for this dataset. Train from the Data & models page first.", 409)
        # Only application-owned artifacts are loaded, never user-uploaded pickle files.
        bundle = joblib.load(path)
        if bundle.get("version") != MODEL_VERSION:
            raise ProjectError("Model format changed. Retrain this dataset.", 409)
        return bundle

    def report(self, mode):
        return self.bundle(mode)["report"]

    def backtest(self, mode, series_ids=None):
        """Three expanding-prefix experiments; each uses its own earlier-only data.

        These are retrospective experiments, not independent evidence of future
        income gains. Keep live model artifacts unchanged.
        """
        if not self.lock.acquire(blocking=False):
            raise ProjectError("Another training/backtest job is running.", 409)
        try:
            raw, excluded = self.training_frame(mode, series_ids)
            dates = sorted(raw.date.unique())
            if len(dates) < 240:
                raise ProjectError("Rolling backtests need at least 240 distinct observed dates.")
            root = self.store.settings.artifacts_dir / "backtests" / mode
            runs = []
            for fraction in (0.65, 0.82, 1.0):
                cutoff = dates[min(len(dates) - 1, int(len(dates) * fraction) - 1)]
                subset = raw[raw.date <= cutoff].copy()
                class WindowStore:
                    settings = Settings(self.store.settings.data_dir, root / cutoff)
                    def frame(self, requested_mode):
                        return subset.copy()
                report = ModelService(WindowStore()).train(mode)
                runs.append({"cutoff": cutoff, "data_rows": len(subset), "splits": report["splits"],
                    "selected_regressor": report["selected_regressor"], "selected_classifier": report["selected_classifier"],
                    "test_regression": report["test_regression"], "test_persistence": report["test_persistence"],
                    "test_mae_skill": report["test_mae_skill"], "test_risk": report["test_risk"],
                    "test_risk_baseline": report["test_risk_baseline"], "warnings": report["warnings"]})
            result = {"mode": mode, "synthetic": mode == "demo", "runs": runs,
                "training_series_ids": sorted(raw.series_id.unique()), "excluded_series_ids": excluded,
                "method": "Expanding data prefixes (65%, 82%, 100%), with independent chronological train/validation/test and seven-day embargo inside each prefix.",
                "note": "Retrospective exploratory backtests; overlapping periods are not independent replicates. No test-based model tuning or farmer-income claim."}
            root.mkdir(parents=True, exist_ok=True)
            (root / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
        finally:
            self.lock.release()

    def forecasts(self, mode, as_of=None, historical=False):
        bundle = self.bundle(mode)
        raw = self.store.frame(mode)
        as_of = as_of or today_ist()
        if historical:
            test = bundle["report"]["splits"]["test"]
            if not pd.Timestamp(test["start"]).date() <= as_of <= pd.Timestamp(test["end"]).date():
                raise ProjectError("Historical replay date must fall within the held-out test period; earlier dates would use future-trained models.")
            raw = raw[pd.to_datetime(raw.date).dt.date <= as_of].copy()
        features = make_features(raw)
        items, withheld = [], []
        for meta in bundle["series"]:
            sid = meta["series_id"]
            observations = raw[raw.series_id == sid]
            if observations.empty:
                withheld.append({**meta, "reason": "No observations."})
                continue
            last = observations.iloc[-1]
            age = (as_of - pd.Timestamp(last.date).date()).days
            rows = features[features.series_id == sid]
            if age < 0 or age > MAX_AGE_DAYS:
                withheld.append({**meta, "reason": f"Latest report is {age} days old; require 0–{MAX_AGE_DAYS} days.", "last_date": last.date})
                continue
            if rows.empty or rows.date.max() != pd.Timestamp(last.date):
                withheld.append({**meta, "reason": "Insufficient recent history for current features."})
                continue
            x = rows.tail(1)[FEATURES + ["series_id"]]
            pred = max(1.0, float(bundle["regressor"].predict(x)[0]) if bundle["regressor"] is not None else float(last.modal_price))
            p = positive_probability(bundle["classifier"], x)
            if bundle["calibration"] is not None:
                p = bundle["calibration"].predict_proba(probability_features(p))[:, 1]
            qlo, qhi = bundle["residual_quantiles"]
            items.append({**meta, "observation_date": last.date, "age_days": age,
                "forecast_date": (pd.Timestamp(last.date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                "current_price": round(float(last.modal_price), 2), "forecast_price": round(pred, 2),
                "interval_low": round(max(1, pred + qlo), 2), "interval_high": round(max(1, pred + qhi), 2),
                "drop_probability": round(float(p[0]), 4), "alert": bool(p[0] >= bundle["report"]["alert_probability_threshold"]),
                "calibration": bundle["report"]["calibration"], "source": last.source})
        known = {m["series_id"] for m in bundle["series"]}
        for sid, group in raw.groupby("series_id"):
            if sid not in known:
                withheld.append({"series_id": sid, "market": group.iloc[-1].market, "reason": "Not represented in training. Import sufficient history and retrain."})
        return {"mode": mode, "synthetic": mode == "demo", "as_of": str(as_of), "historical_replay": historical, "items": items,
                "withheld": withheld, "model_trained_at": bundle["report"]["trained_at"], "warnings": bundle["report"]["warnings"]}

    def compare(self, mode, quantity, selections, replay_date=None):
        if not np.isfinite(quantity) or quantity <= 0 or quantity > 100_000:
            raise ProjectError("Quantity must be finite, positive, and at most 100,000 quintals.")
        if not 2 <= len(selections) <= 20:
            raise ProjectError("Select between 2 and 20 markets.")
        if len({s["series_id"] for s in selections}) != len(selections):
            raise ProjectError("Markets must not be repeated.")
        forecasts = self.forecasts(mode, as_of=replay_date, historical=True) if replay_date else self.forecasts(mode)
        available = {r["series_id"]: r for r in forecasts["items"]}
        rows = []
        for selection in selections:
            forecast = available.get(selection["series_id"])
            if forecast is None:
                raise ProjectError("A selected market has no fresh supported forecast.")
            costs = float(selection["transport_cost"]) + float(selection["market_fees"])
            if any(not np.isfinite(float(selection[k])) or float(selection[k]) < 0 for k in ("transport_cost", "market_fees")):
                raise ProjectError("Costs must be finite, nonnegative total amounts in INR.")
            rows.append({**forecast, "quantity_quintals": quantity, "total_cost": costs,
                "estimated_net_revenue": round(quantity * forecast["forecast_price"] - costs, 2),
                "net_interval_low": round(quantity * forecast["interval_low"] - costs, 2),
                "net_interval_high": round(quantity * forecast["interval_high"] - costs, 2)})
        signature = {(r["commodity"].casefold(), r["variety"].casefold(), r["grade"].casefold(), r["unit"], r["forecast_date"]) for r in rows}
        if len(signature) != 1:
            raise ProjectError("Compare the same crop, variety, grade, unit, and forecast date only.")
        if mode == "real" and replay_date is None and any(r["grade"].casefold() == "unspecified" for r in rows):
            raise ProjectError("Source grade is unreported. Live selling comparison requires verified equivalent grade; historical replay is available for research only.")
        rows.sort(key=lambda r: r["estimated_net_revenue"], reverse=True)
        overlap = rows[0]["net_interval_low"] <= max(r["net_interval_high"] for r in rows[1:])
        return {"mode": mode, "synthetic": mode == "demo", "forecast_date": rows[0]["forecast_date"],
            "historical_replay": replay_date is not None,
            "quantity_quintals": quantity, "rows": rows, "intervals_overlap": overlap,
            "note": ("HISTORICAL RESEARCH REPLAY, not current selling advice. Unreported grade and broad source varieties do not establish equal produce quality. " if replay_date else "") + "These are model-based wholesale revenue estimates, not guaranteed prices or profit. Production costs are excluded. Overlapping intervals mean the ranking is uncertain."}
