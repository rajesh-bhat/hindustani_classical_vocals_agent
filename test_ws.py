import asyncio
import websockets
import json

async def run_scenario(websocket, query, scenario_name):
    print(f"\n--- Running Scenario: {scenario_name} ---")
    print(f"User: {query}")
    await websocket.send(json.dumps({"text": query}))
    
    # Listen for responses for up to 12 seconds per test
    end_time = asyncio.get_event_loop().time() + 12.0
    full_response = ""
    
    while True:
        remain = end_time - asyncio.get_event_loop().time()
        if remain <= 0:
            break
            
        try:
            message_str = await asyncio.wait_for(websocket.recv(), timeout=remain)
            message = json.loads(message_str)
            
            if "debug_tool" in message:
                print(f"[METRIC] Agent Loaded Tool -> {message['debug_tool']}({message.get('debug_args', {})})")
                
            if "output_text" in message:
                full_response += message["output_text"]
                
        except asyncio.TimeoutError:
            break
        except Exception as e:
            print(f"Error receiving: {e}")
            break
            
    print(f"Agent: {full_response.strip().replace('  ', ' ')}")

async def run_all_tests():
    uri = "ws://localhost:8002/ws/live"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to actual live server API.")
            
            tests = [
                ("Tell me about Darbari.", "Core Lookup & Normalization"),
                ("In Raag Yaman, can I sing Sa directly to Pa in the aaroh?", "Deep Structural Rules (Chalan)"),
                ("What is the difference between Bhupali and Deshkar?", "Comparative Musicology (Dual Lookup)"),
                ("Which are the 10 Hindustani thaats?", "Fundamental Theory"),
                ("What is the weather like in Mumbai today?", "Domain Boundary Enforcement")
            ]
            
            for query, name in tests:
                await run_scenario(websocket, query, name)
                await asyncio.sleep(1) # tiny gap between turns
                
            print("\nAll live tests complete. Sending stream end.")
            await websocket.send(json.dumps({"audioStreamEnd": True}))
            
    except Exception as e:
        print(f"Failed to connect or test: {e}")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
