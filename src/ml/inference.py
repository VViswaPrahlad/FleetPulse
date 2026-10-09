"""Trusted local model loading and strict, metadata-free feature inference."""
import json

import joblib
import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from src.analytics.build_gold import local,sha256
from src.features.speed_windows import FEATURES
from src.ml.train_speed import MODEL_PATH


def load_model(path=MODEL_PATH):
    path=local(path)
    metadata_path=path.parent/'inference_metadata.json'
    metadata=json.loads(metadata_path.read_text())
    if metadata['feature_order']!=list(FEATURES):
        raise ValueError('Inference feature order/version mismatch')
    if metadata['versions']['scikit-learn']!=sklearn.__version__:
        raise ValueError('Model requires the recorded scikit-learn version')
    if sha256(path)!=metadata['model_sha256']:
        raise ValueError('Model integrity mismatch')
    # Integrity hash is not authentication: only load artifacts produced locally
    # by the trusted training script. Joblib is not a safe untrusted-file format.
    return joblib.load(path),metadata


def predict_features(frame,model,path_metadata=None):
    if len(frame.columns)!=len(FEATURES) or set(frame.columns)!=set(FEATURES):
        raise ValueError('Exactly the approved predictive columns required; no IDs/target')
    ordered=frame.loc[:,list(FEATURES)].astype(float)
    if np.isinf(ordered.to_numpy()).any():
        raise ValueError('Infinite feature input; NaN missing values allowed')
    with threadpool_limits(limits=1):
        result=model.predict(ordered)
    if not np.isfinite(result).all():
        raise ValueError('Model returned nonfinite predictions')
    return result
