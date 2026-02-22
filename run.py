#!/usr/bin/env python3
"""
Script para executar o servidor do agent de venda
"""
import asyncio

from src.main import main

if __name__ == "__main__":
    asyncio.run(main())
