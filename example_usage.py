#Пример использования DroneSimulator.

from src.drone_simulator import DroneSimulator


def main():
    # Создаем симулятор дрона
    drone = DroneSimulator(
        drone_id="drone_001",
        name="Test Drone",
        initial_battery=80.0
    )
    
    print("\n=== Получение состояния ===")
    state = drone.get_state()
    print(f"Статус: {state['status']}")
    print(f"Батарея: {state['battery']}%")
    print(f"Позиция: {state['position']}")
    
    print("\n=== Взлет ===")
    result = drone.takeoff(altitude=15.0)
    if result["success"]:
        print(f"Дрон взлетел на высоту {result['altitude']} метров")
    else:
        print(f"Ошибка: {result['error']}")
    
    print("\n=== Движение ===")
    result = drone.move(
        target_position={"x": 10.0, "y": 20.0, "z": 15.0},
        speed=8.0
    )
    if result["success"]:
        print(f"Дрон переместился в позицию {result['position']}")
        print(f"Батарея: {result['battery']}%")
    
    print("\n=== Посадка ===")
    result = drone.land(
        position={"x": 10.0, "y": 20.0},
        droneport_id="droneport_001"
    )
    if result["success"]:
        print(f"Дрон приземлился в дронопорте {result['droneport_id']}")
    
    print("\n=== Зарядка ===")
    result = drone.charge(target_level=100.0)
    if result["success"]:
        print(f"Дрон заряжен до {result['battery']}%")
    
    print("\n=== Финальное состояние ===")
    state = drone.get_state()
    print(f"Статус: {state['status']}")
    print(f"Батарея: {state['battery']}%")
    print(f"Всего полетов: {state['total_flights']}")


if __name__ == "__main__":
    main()

