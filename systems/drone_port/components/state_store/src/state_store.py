import redis

class StateStore:
    def __init__(self, host="localhost", port=6379):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)

    def save_drone(self, drone_id: str,  dict):
        self.redis.hset(f"drone:{drone_id}", mapping=data)

    def get_drone(self, drone_id: str) -> dict:
        return self.redis.hgetall(f"drone:{drone_id}")

    def list_drones(self) -> list:
        keys = self.redis.keys("drone:*")
        return [self.redis.hgetall(k) for k in keys]

    def reserve_port(self, port_id: str, drone_id: str):
        self.redis.set(f"port:{port_id}", drone_id)

    def release_port(self, port_id: str):
        self.redis.delete(f"port:{port_id}")