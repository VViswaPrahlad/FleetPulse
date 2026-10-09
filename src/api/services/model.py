from threading import RLock

import pandas as pd

from src.api.errors import unavailable
from src.features.speed_windows import FEATURES


class ModelService:
    def __init__(self,settings):
        self.settings=settings
        self._signature=None
        self._model=None
        self._metadata=None
        self._lock=RLock()

    def _load(self):
        try:
            paths=(self.settings.model,self.settings.model.parent/'inference_metadata.json')
            signature=tuple((p.stat().st_mtime_ns,p.stat().st_size) for p in paths)
            if signature!=self._signature or self._model is None:
                from src.ml.inference import load_model
                model,metadata=load_model(self.settings.model)
                if metadata.get('history_seconds')!=60 or metadata.get('forecast_seconds')!=60 or metadata.get('max_sampling_gap_ms')!=2000 or metadata.get('units')!='km/h':
                    raise ValueError('Model temporal/unit contract differs')
                self._model,self._metadata,self._signature=model,metadata,signature
        except Exception:
            self._model=None
            self._metadata=None
            self._signature=None
            raise unavailable('model') from None

    def ready(self):
        try:
            with self._lock:
                self._load()
            return True
        except Exception:
            return False

    def predict(self,features):
        # Nullable optional means are converted to NaN by pandas; no filling.
        frame=pd.DataFrame([features],columns=list(FEATURES),dtype=float)
        with self._lock:
            self._load()
            from src.ml.inference import predict_features
            try:
                predicted=predict_features(frame,self._model)[0]
                return float(predicted),'hgb-day6-'+self._metadata['model_sha256'][:12]
            except Exception:
                raise unavailable('model') from None

    def identity(self):
        with self._lock:
            self._load()
            return 'hgb-day6-'+self._metadata['model_sha256'][:12]
