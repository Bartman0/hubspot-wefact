import os
import uuid
from typing import Dict, Optional

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


def execute_docker_container(task_id: str, image: str, command: str):
    """
    The worker function that runs in the background.
    """
    try:
        tasks[task_id]["status"] = STATUS_RUNNING

        # Run the container
        container = client.containers.run(
            image=image,
            command=command,
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
    image: str = IMAGE,
    command: Optional[str] = None,
    token: str = Depends(verify_api_key),
):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": STATUS_QUEUED, "image": image}

    # Schedule the docker run to happen in the background
    background_tasks.add_task(execute_docker_container, task_id, image, command)

    return {
        "task_id": task_id,
        "status": tasks[task_id]["status"],
        "message": "Hubspot-Wefact execution started in background",
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, token: str = Depends(verify_api_key)):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]
