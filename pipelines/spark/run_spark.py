"""Compile (scalac via coursier-fetched compiler) and run the Scala Spark CURATE job locally.

Runs the job with plain `java` and Spark's jars on the classpath instead of spark-submit.cmd,
because the Windows batch launcher breaks on the '&' character in this project's path.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from orbit_core.config import PATHS

SPARK_DIR = Path(__file__).resolve().parent
SRC = SPARK_DIR / "src" / "main" / "scala"
BUILD = SPARK_DIR / "build"
SPARK_HOME = Path(os.environ.get("SPARK_HOME", PATHS.tools / "spark-4.0.4-bin-hadoop3"))
SCALAC_CP_FILE = PATHS.tools / "scalac.cp"
SCALA_VERSION = "2.13.16"  # must match jars/scala-library-*.jar shipped with Spark 4.0.4
JAVA_OPENS = [
    "--add-opens=java.base/java.lang=ALL-UNNAMED", "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
    "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED", "--add-opens=java.base/java.io=ALL-UNNAMED",
    "--add-opens=java.base/java.net=ALL-UNNAMED", "--add-opens=java.base/java.nio=ALL-UNNAMED",
    "--add-opens=java.base/java.util=ALL-UNNAMED", "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED",
    "--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED", "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
    "--add-opens=java.base/sun.nio.cs=ALL-UNNAMED", "--add-opens=java.base/sun.security.action=ALL-UNNAMED",
    "--add-opens=java.base/sun.util.calendar=ALL-UNNAMED", "-Djdk.reflect.useDirectMethodHandle=false",
    "-Dio.netty.tryReflectionSetAccessible=true",
]


def _spark_cp() -> str:
    return str(SPARK_HOME / "jars" / "*")


def scalac_classpath() -> str:
    """Resolve the Scala 2.13 compiler (matching Spark's Scala) with the project-local coursier."""
    if SCALAC_CP_FILE.exists():
        raw = SCALAC_CP_FILE.read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
        lines = [ln for ln in text.strip().splitlines() if "scala-compiler" in ln]
        if lines:
            return lines[-1].strip()
    out = subprocess.run(["java", "-jar", str(PATHS.tools / "dl" / "coursier.jar"), "fetch", "--classpath",
                          f"org.scala-lang:scala-compiler:{SCALA_VERSION}"], check=True, capture_output=True,
                         text=True).stdout.strip()
    SCALAC_CP_FILE.write_text(out, encoding="utf-8")
    return out


def compile_job() -> Path:
    classes = BUILD / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in SRC.rglob("*.scala"))
    newest_src = max(Path(s).stat().st_mtime for s in sources)
    marker = classes / "orbit" / "CurateJob.class"
    if marker.exists() and marker.stat().st_mtime > newest_src:
        return classes
    scalac_cp = scalac_classpath()
    cmd = ["java", "-cp", scalac_cp, "scala.tools.nsc.Main", "-classpath", _spark_cp(), "-d", str(classes),
           "-deprecation", *sources]
    subprocess.run(cmd, check=True)
    return classes


def run_curate(conformed: Path = PATHS.curated / "conformed", marts: Path = PATHS.curated / "marts",
               cutoff: str = "2025-09-30") -> dict:
    classes = compile_job()
    cp = os.pathsep.join([str(classes), _spark_cp()])
    env = dict(os.environ)
    env.setdefault("HADOOP_HOME", str(PATHS.tools / "hadoop"))
    env["PATH"] = str(Path(env["HADOOP_HOME"]) / "bin") + os.pathsep + env.get("PATH", "")
    cmd = ["java", "-Xmx3g", *JAVA_OPENS, f"-Dhadoop.home.dir={env['HADOOP_HOME']}", "-cp", cp,
           "orbit.CurateJob", conformed.as_posix(), marts.as_posix(), cutoff]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-40:])
        raise RuntimeError(f"Spark job failed (exit {proc.returncode}):\n{tail}")
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("CURATE_RESULT "))
    return json.loads(line[len("CURATE_RESULT "):])


if __name__ == "__main__":
    print(json.dumps(run_curate(), indent=2))
