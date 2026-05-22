from systems.drone_port.src.gateway.src.gateway import DronePortGateway
from systems.drone_port.src.gateway.topics import ComponentTopics, ExternalTopics, GatewayActions, SystemTopics


def test_gateway_registers_all_routes(mock_bus):
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)

    assert GatewayActions.GET_AVAILABLE_DRONES not in gateway._handlers
    assert GatewayActions.REQUEST_LANDING not in gateway._handlers
    assert GatewayActions.REQUEST_TAKEOFF not in gateway._handlers
    assert GatewayActions.PROXY_REQUEST in gateway._handlers
    assert GatewayActions.PROXY_PUBLISH in gateway._handlers
    assert GatewayActions.LIST_POLICIES in gateway._handlers
    assert gateway.topic == SystemTopics.DRONE_PORT


def test_gateway_proxy_request_checks_policy_and_routes_to_drone_manager(mock_bus):
    mock_bus.request.return_value = {"approved": True, "port_id": "P-01"}
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)

    result = gateway._handle_proxy_request(
        {
            "sender": ExternalTopics.AGRODRON,
            "payload": {
                "target": {
                    "topic": ExternalTopics.DRONE_PORT,
                    "action": GatewayActions.REQUEST_LANDING,
                },
                "data": {"drone_id": "DR-1"},
            },
        }
    )

    assert result == {"target_response": {"approved": True, "port_id": "P-01"}}
    mock_bus.request.assert_called_once_with(
        ComponentTopics.DRONE_MANAGER,
        {
            "action": GatewayActions.REQUEST_LANDING,
            "sender": "drone_port",
            "payload": {"drone_id": "DR-1"},
        },
        timeout=10.0,
    )


def test_gateway_proxy_publish_routes_to_sitl(monkeypatch, mock_bus):
    monkeypatch.setenv("SITL_HOME_TOPIC", "sitl")
    mock_bus.publish.return_value = True
    gateway = DronePortGateway(system_id="drone_port", bus=mock_bus)

    result = gateway._handle_proxy_publish(
        {
            "sender": ExternalTopics.DRONE_PORT,
            "payload": {
                "target": {
                    "topic": ExternalTopics.SITL,
                    "action": GatewayActions.SITL_HOME_PUBLISH,
                },
                "data": {"drone_id": "DR-1", "home_lat": 1.0, "home_lon": 2.0, "home_alt": 3.0},
            },
        }
    )

    assert result == {"published": True}
    mock_bus.publish.assert_called_once_with(
        "sitl",
        {"drone_id": "DR-1", "home_lat": 1.0, "home_lon": 2.0, "home_alt": 3.0},
    )
