class ApiError(Exception):
    def __init__(self,status,code,message):
        self.status=status
        self.code=code
        self.message=message
        super().__init__(code)


def unavailable(component):
    return ApiError(503,f'{component}_unavailable',{
        'analytics':'Fleet analytics are unavailable.',
        'model':'The forecasting model is unavailable.',
        'evaluation':'Saved model evaluation is unavailable.'}[component])
