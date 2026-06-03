from __future__ import annotations

from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse

from ..perf.lab_models import PerfRunRequest


def register_perf_lab_routes(app, require_admin):
    @app.post("/admin/perf/runs")
    async def create_perf_run(request: Request):
        require_admin(request)
        try:
            payload = await request.json()
            run_request = PerfRunRequest(**payload)
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = request.app.state.perf_lab_runner.create_run(run_request)
        if result.get("status_code") == 409:
            raise HTTPException(status_code=409, detail=result["detail"])
        return JSONResponse({"run": result})

    @app.get("/admin/perf/runs")
    async def list_perf_runs(request: Request):
        require_admin(request)
        return JSONResponse({"runs": request.app.state.perf_lab_runner.list_runs()})

    @app.get("/admin/perf/runs/{run_id}")
    async def get_perf_run(request: Request, run_id: str):
        require_admin(request)
        try:
            run = request.app.state.perf_lab_runner.get_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="perf_run_not_found") from exc
        return JSONResponse({"run": run})

    @app.get("/admin/perf/runs/{run_id}/samples")
    async def get_perf_samples(request: Request, run_id: str, point_id: str | None = None):
        require_admin(request)
        try:
            samples = request.app.state.perf_lab_runner.store.read_samples(run_id, point_id=point_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="perf_run_not_found") from exc
        return JSONResponse({"samples": samples})

    @app.post("/admin/perf/runs/{run_id}/cancel")
    async def cancel_perf_run(request: Request, run_id: str):
        require_admin(request)
        try:
            run = request.app.state.perf_lab_runner.cancel_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="perf_run_not_found") from exc
        return JSONResponse({"run": run})
