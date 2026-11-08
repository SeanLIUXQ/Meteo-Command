"""WSGI entry point. Run ``python run.py`` for the local launcher."""

from meteo.backend import analyze_risks, create_app, get_wind_direction

app = create_app()


if __name__ == "__main__":
    from run import main

    raise SystemExit(main())
