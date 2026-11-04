"""Accounts: sign up, sign in, profile, and who may see and change a plot."""

import uuid

import pytest
from fastapi.testclient import TestClient

from elderleaf.app import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def device() -> dict:
    return {"X-Device-Id": f"d_{uuid.uuid4().hex[:12]}"}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def new_plot(client, headers, name="Bed 1"):
    resp = client.post("/plots", json={"name": name, "crop": "lettuce", "area_m2": 4}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def sign_up(client, headers, email=None, password="garden-pass-1", **extra):
    body = {"email": email or f"{uuid.uuid4().hex[:8]}@example.com", "password": password, "name": "Ayşe", **extra}
    return client.post("/auth/signup", json=body, headers=headers)


def test_sign_up_moves_guest_plots_into_the_account(client):
    phone = device()
    plot_id = new_plot(client, phone)

    resp = sign_up(client, phone, garden="METU Bostan", experience="few_seasons")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["claimed_plots"] == 1
    assert body["user"]["garden"] == "METU Bostan"
    assert body["user"]["experience"] == "few_seasons"
    token = body["token"]

    mine = [p["id"] for p in client.get("/plots", headers=bearer(token)).json() if not p["is_demo"]]
    assert mine == [plot_id]
    # the plot left the guest device: without the token it is gone from the list and read-only
    assert plot_id not in [p["id"] for p in client.get("/plots", headers=phone).json()]
    assert client.post(f"/plots/{plot_id}/notes", json={"kind": "observation", "date": "2026-11-01", "text": "x"}, headers=phone).status_code == 403
    assert client.post(f"/plots/{plot_id}/notes", json={"kind": "observation", "date": "2026-11-01", "text": "x"}, headers=bearer(token)).status_code == 201


def test_sign_in_on_a_second_device_sees_the_same_plots(client):
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    first = sign_up(client, device(), email=email).json()
    plot_id = new_plot(client, bearer(first["token"]))

    laptop = device()
    assert client.post("/auth/login", json={"email": email.upper(), "password": "wrong-password"}, headers=laptop).status_code == 401
    resp = client.post("/auth/login", json={"email": f"  {email.upper()} ", "password": "garden-pass-1"}, headers=laptop)
    assert resp.status_code == 200, resp.text
    assert plot_id in [p["id"] for p in client.get("/plots", headers=bearer(resp.json()["token"])).json()]


def test_duplicate_email_and_bad_input(client):
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    assert sign_up(client, device(), email=email).status_code == 201
    assert sign_up(client, device(), email=email.upper()).status_code == 409
    assert sign_up(client, device(), email="not-an-email").status_code == 422
    assert sign_up(client, device(), password="short").status_code == 422


def test_profile_and_stats(client):
    resp = sign_up(client, device())
    token = resp.json()["token"]
    new_plot(client, bearer(token))

    me = client.get("/me", headers=bearer(token)).json()
    assert me["name"] == "Ayşe"
    assert me["stats"]["plots"] == 1 and me["stats"]["photos"] == 0

    resp = client.patch("/me", json={"name": "Ayşe K.", "garden": "METU Bostan", "experience": "experienced"}, headers=bearer(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["garden"] == "METU Bostan"
    resp = client.patch("/me", json={"garden": None}, headers=bearer(token))
    assert resp.json()["garden"] is None and resp.json()["name"] == "Ayşe K."


def test_logout_ends_the_session(client):
    token = sign_up(client, device()).json()["token"]
    assert client.get("/me", headers=bearer(token)).status_code == 200
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/me", headers=bearer(token)).status_code == 401
    assert client.get("/me").status_code == 401


def test_a_device_id_cannot_pose_as_an_account(client):
    body = sign_up(client, device()).json()
    plot_id = new_plot(client, bearer(body["token"]))
    fake = {"X-Device-Id": body["user"]["id"]}
    assert plot_id not in [p["id"] for p in client.get("/plots", headers=fake).json()]
    assert client.delete(f"/plots/{plot_id}", headers=fake).status_code == 403


def test_password_is_stored_hashed(client):
    from sqlalchemy import select

    from elderleaf.db import SessionLocal, User

    email = f"{uuid.uuid4().hex[:8]}@example.com"
    sign_up(client, device(), email=email)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user.password_hash.startswith("scrypt$") and "garden-pass-1" not in user.password_hash
