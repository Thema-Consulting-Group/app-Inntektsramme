import yaml 

class Util:
    """Utility class """
    @staticmethod
    def load_config(path) -> dict:
        with open(path, 'r') as file:
            config: dict = yaml.safe_load(file)
        return config
