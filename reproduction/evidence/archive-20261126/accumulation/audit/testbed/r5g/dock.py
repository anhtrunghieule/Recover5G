"""Thin wrappers around the docker CLI (stdlib only)."""
import os
import subprocess
import time

DOCKER_CONTEXT = os.environ.get("DOCKER_CONTEXT", "colima-recover5g")
ENV = dict(os.environ, DOCKER_CONTEXT=DOCKER_CONTEXT)
TESTBED = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(args, check=True, timeout=120, capture=True, env=None):
    e = dict(ENV)
    if env:
        e.update(env)
    r = subprocess.run(args, capture_output=capture, text=True, timeout=timeout, env=e)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def docker(*args, check=True, timeout=120):
    return sh(["docker", *args], check=check, timeout=timeout)


def dexec(container, cmd, check=False, timeout=30):
    """Run `cmd` (str, through sh -c) inside a container; return CompletedProcess."""
    return sh(["docker", "exec", container, "sh", "-c", cmd], check=check, timeout=timeout)


def compose_file():
    inst = int(os.environ.get("R5G_INST", "0"))
    return os.path.join(TESTBED, "docker-compose.yml") if inst == 0 else \
        os.path.join(TESTBED, "inst", str(inst), "docker-compose.yml")


def compose(*args, env=None, check=True, timeout=300):
    return sh(["docker", "compose", "-f", compose_file(), *args],
              check=check, timeout=timeout, env=env)


def kill(container):
    """SIGKILL the container's PID 1 tree (volatile state lost)."""
    t = time.time()
    docker("kill", "-s", "KILL", container, check=False)
    return t


def start(container):
    docker("start", container, check=False)
    return time.time()


def pause(container):
    docker("pause", container, check=False)
    return time.time()


def unpause(container):
    docker("unpause", container, check=False)
    return time.time()


def running(container):
    r = docker("inspect", "-f", "{{.State.Running}}", container, check=False)
    return r.stdout.strip() == "true"


def logs(container, since=None):
    args = ["logs", "--timestamps"]
    if since is not None:
        args += ["--since", f"{since:.3f}"]
    r = docker(*args, container, check=False, timeout=60)
    return r.stdout + r.stderr


def image_id(image):
    r = docker("image", "inspect", "-f", "{{.Id}}", image, check=False)
    return r.stdout.strip()
