from systems.drone_port.src.gateway.src.gateway import DronePortGateway
from systems.drone_port.src.gateway.topics import ExternalTopics, GatewayActions, SystemTopics
from systems.drone_port.src.security_monitor.topics import ComponentTopics as SecurityMonitorTopics


def test_gateway_registers_only_proxy_routes(mock_bus):
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)

    assert GatewayActions.GET_AVAILABLE_DRONES not in gateway._handlers
    assert GatewayActions.REQUEST_LANDING not in gateway._handlers
    assert GatewayActions.REQUEST_TAKEOFF not in gateway._handlers
    assert GatewayActions.PROXY_REQUEST in gateway._handlers
    assert GatewayActions.PROXY_PUBLISH in gateway._handlers
    assert GatewayActions.LIST_POLICIES in gateway._handlers
    assert gateway.topic == SystemTopics.DRONE_PORT


def test_gateway_proxy_request_delegates_to_security_monitor(mock_bus):
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)
    message = {
        "action": GatewayActions.PROXY_REQUEST,
        "sender": ExternalTopics.AGRODRON,
        "payload": {
            "target": {
                "topic": ExternalTopics.DRONE_PORT,
                "action": GatewayActions.REQUEST_LANDING,
            },
            "data": {"drone_id": "DR-1"},
        },
    }
    mock_bus.request.return_value = {"payload": {"target_response": {"approved": True, "port_id": "P-01"}}}

    result = gateway._handle_proxy_request(message)

    assert result == {"target_response": {"approved": True, "port_id": "P-01"}}
    mock_bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        message,
        timeout=10.0,
    )


def test_gateway_proxy_publish_delegates_to_security_monitor(mock_bus):
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)
    message = {
        "action": GatewayActions.PROXY_PUBLISH,
        "sender": ExternalTopics.DRONE_PORT,
        "payload": {
            "target": {
                "topic": ExternalTopics.SITL,
                "action": GatewayActions.SITL_HOME_PUBLISH,
            },
            "data": {"drone_id": "DR-1", "home_lat": 1.0, "home_lon": 2.0, "home_alt": 3.0},
        },
    }
    mock_bus.request.return_value = {"payload": {"published": True}}

    result = gateway._handle_proxy_publish(message)

    assert result == {"published": True}
    mock_bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        message,
        timeout=10.0,
    )
