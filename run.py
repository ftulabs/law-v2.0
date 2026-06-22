#!/usr/bin/env python3
"""VeriTrade — canonical entry point expected by the hackathon reviewer script.

    python run.py --country SG --pillar 6
    python run.py --country Malaysia --pillar 7 --live --llm openrouter

Accepts --country as an alias for --economy; all other flags are forwarded to main.py.
"""
import sys

if __name__ == "__main__":
    args = sys.argv[1:]
    # replace --country with --economy so the main parser accepts it
    fixed = []
    i = 0
    while i < len(args):
        if args[i] == "--country":
            fixed.append("--economy")
        else:
            fixed.append(args[i])
        i += 1
    sys.argv[1:] = fixed
    from main import main
    main()
