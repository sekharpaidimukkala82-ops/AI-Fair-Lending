"""
Fair Lending Platform - Windows launcher for uvicorn 0.29+
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set Windows SelectorEventLoop — more stable with uvicorn + background tasks on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def serve():
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    config = uvicorn.Config(
        app="backend.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        reload=False,
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Fair Lending Intelligence Platform")
    print("  API   -> http://localhost:8001")
    print("  Docs  -> http://localhost:8001/docs")
    print("  Press Ctrl+C to stop")
    print("="*55 + "\n")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(serve())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except OSError as e:
        print(f"\nPORT ERROR: {e}")
        print("Run: taskkill /F /IM python.exe  then try again.")
        input("Press Enter...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("\nPress Enter...")
    finally:
        loop.close()
