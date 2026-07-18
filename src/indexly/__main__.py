# src/indexly/__main__.py


def main():
    from indexly.rename_watch.status_cli import maybe_run_status

    result = maybe_run_status()
    if result is not None:
        return result

    from indexly.indexly import main as application_main

    return application_main()


if __name__ == "__main__":
    raise SystemExit(main())
