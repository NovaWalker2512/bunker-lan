from bunker.ui.app import create_app


def main() -> None:
    """Start the Bunker LAN desktop application."""
    app = create_app()
    app.mainloop()


if __name__ == "__main__":
    main()
