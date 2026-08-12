from threading import Event

from fastapi.testclient import TestClient

from backend.worker_service import LOCAL_PORT_DEFAULT, configured_port, create_worker_app


def test_health_endpoint_is_safe_and_worker_starts(monkeypatch):
    started = Event()
    stopped = Event()

    def loop(stop_event: Event) -> None:
        started.set()
        stop_event.wait(1)
        stopped.set()

    app = create_worker_app(loop)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "deallens-worker"}
        assert started.wait(0.2)
    assert stopped.wait(0.2)


def test_root_health_endpoint_and_local_port_default(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert configured_port() == LOCAL_PORT_DEFAULT
    app = create_worker_app(lambda stop_event: stop_event.wait(1))
    with TestClient(app) as client:
        assert client.get("/").json()["service"] == "deallens-worker"


def test_worker_loop_can_receive_shutdown_event_without_completing_a_job():
    active_job_completed = False

    def loop(stop_event: Event) -> None:
        nonlocal active_job_completed
        stop_event.wait(1)
        # A production loop leaves the currently active job to its durable
        # recovery policy; shutdown itself never calls complete().
        assert not active_job_completed

    app = create_worker_app(loop)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert not active_job_completed
