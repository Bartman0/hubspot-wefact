import os
import uuid
from typing import Dict

import docker
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from auth import verify_api_key

HOST_DATA_PATH = os.environ["HOST_DATA_PATH"]
HUBSPOT_ACCESS_TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
WEFACT_API_KEY = os.environ["WEFACT_API_KEY"]

IMAGE = "creathlon/hubspot-wefact"

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = docker.from_env()

# In-memory store for task status (in production, use Redis or a database)
tasks: Dict[str, dict] = {}


def execute_docker_container(task_id: str, image: str):
    """Run one sync container to completion and record the outcome under task_id.

    Runs in a FastAPI background thread, so blocking on the container is fine.
    The HubSpot and WeFact credentials of this service are passed into the
    container and the host data directory is mounted at /app/data so the state
    database survives the run. The container is removed afterwards; its exit
    code and captured logs are stored in the tasks dict. Any failure is
    recorded as STATUS_FAILED with the exception text rather than raised.

    No command is passed, so the image always runs its own CMD (the sync run).
    Deliberately not configurable: the container holds live HubSpot and WeFact
    credentials, and its logs are handed back to the caller, so an overridable
    command would let any caller read those secrets straight out of the run.
    """
    try:
        tasks[task_id]["status"] = STATUS_RUNNING

        # Run the container
        container = client.containers.run(
            image=image,
            environment={
                "HUBSPOT_ACCESS_TOKEN": HUBSPOT_ACCESS_TOKEN,
                "WEFACT_API_KEY": WEFACT_API_KEY,
            },
            detach=True,
            volumes={
                HOST_DATA_PATH: {
                    "bind": "/app/data",
                    "mode": "rw",
                }
            },
        )

        # Wait for the result (this blocks the background thread, not the API)
        result = container.wait()
        logs = container.logs().decode("utf-8")

        tasks[task_id].update(
            {
                "status": STATUS_COMPLETED,
                "exit_code": result["StatusCode"],
                "output": logs.strip(),
            }
        )

        container.remove()
    except Exception as e:
        tasks[task_id].update({"status": STATUS_FAILED, "error": str(e)})


@app.post("/tasks", status_code=202)
async def create_task(
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_api_key),
):
    """Queue a sync run and return immediately with 202 and its task id.

    The container is started in the background; poll GET /tasks/{task_id} for
    the result. Requires a valid bearer token. There are no request parameters:
    both the image and the command it runs are fixed.
    """
    image = IMAGE
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": STATUS_QUEUED, "image": image}

    # Schedule the docker run to happen in the background
    background_tasks.add_task(execute_docker_container, task_id, image)

    return {
        "task_id": task_id,
        "status": tasks[task_id]["status"],
        "message": "Hubspot-Wefact execution started in background",
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, token: str = Depends(verify_api_key)):
    """Return the status of a queued sync run, with its exit code and logs once finished.

    Raises 404 when the id is unknown. Task state is kept in memory only, so it
    is lost when the service restarts.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]
