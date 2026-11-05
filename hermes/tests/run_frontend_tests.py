"""Run the formal frontend fixture; never exec the production container."""
from run_offline import main


if __name__ == "__main__":
    raise SystemExit(main(frontend_only=True))
