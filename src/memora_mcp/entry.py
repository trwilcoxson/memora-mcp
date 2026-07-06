import sys

# Single console entry. Subcommands run the management CLI / doctor / hooks;
# bare `memora-mcp` runs the MCP stdio server (what Claude/Omnigent spawn).

_CLI_CMDS = {
    "list", "show", "why", "forget", "stats", "export",
    "config", "distill", "doctor", "enable", "disable",
}


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in _CLI_CMDS:
        from memora_mcp.cli import main as cli_main

        cli_main(argv)
        return
    if argv and argv[0] == "hook":
        from memora_mcp.hooks import main as hook_main

        hook_main(argv[1:])
        return
    from memora_mcp.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
