import asyncio
from backend.agents.local_sandbox import LocalSandbox


def test_supervisor_recovers_only_its_owned_process(monkeypatch):
    monkeypatch.setenv("AVENTRA_LOCAL_SANDBOX_ENABLED","true")
    manager=LocalSandbox();started=[]
    class Process:
        returncode=None
        def poll(self):return self.returncode
        def terminate(self):self.returncode=0
        def wait(self,timeout):return self.returncode
    def start():
        manager.process=Process();started.append(manager.process)
    monkeypatch.setattr(manager,"start",start)
    monkeypatch.setattr(manager,"reachable",lambda:manager.process is not None and manager.process.poll() is None)
    async def exercise():
        async with manager:
            assert len(started)==1
            started[0].returncode=1
            await asyncio.sleep(2.2)
            assert len(started)==2
        assert started[1].poll()==0
    asyncio.run(exercise())


def test_supervisor_does_not_replace_existing_listener(monkeypatch):
    monkeypatch.setenv("AVENTRA_LOCAL_SANDBOX_ENABLED","true")
    manager=LocalSandbox()
    monkeypatch.setattr(manager,"reachable",lambda:True)
    def forbidden():raise AssertionError("Existing listener must be left alone")
    monkeypatch.setattr(manager,"start",forbidden)
    async def exercise():
        async with manager:await asyncio.sleep(.01)
        assert manager.process is None
    asyncio.run(exercise())
