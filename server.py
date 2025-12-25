import asyncio
import websockets
import json
import os

td_connection = None
viewers = set()

async def handler(websocket, path):
    global td_connection
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data['type'] == 'td-sender':
                td_connection = websocket
                print('TouchDesigner connected')
                # Сразу говорим сколько viewers
                await websocket.send(json.dumps({
                    'type': 'viewer_count',
                    'count': len(viewers)
                }))
                
            elif data['type'] == 'viewer':
                viewers.add(websocket)
                print(f'Viewer connected. Total: {len(viewers)}')
                
                # Уведомляем TD что появился viewer
                if td_connection:
                    await td_connection.send(json.dumps({
                        'type': 'viewer_count',
                        'count': len(viewers)
                    }))
                
            elif data['type'] == 'frame' and websocket == td_connection:
                # Отправляем только если есть viewers
                if viewers:
                    dead_viewers = set()
                    for viewer in viewers:
                        try:
                            await viewer.send(message)
                        except:
                            dead_viewers.add(viewer)
                    viewers.difference_update(dead_viewers)
                    
    except websockets.exceptions.ConnectionClosed:
        if websocket in viewers:
            viewers.remove(websocket)
            print(f'Viewer disconnected. Total: {len(viewers)}')
            
            # Уведомляем TD что viewer ушел
            if td_connection:
                try:
                    await td_connection.send(json.dumps({
                        'type': 'viewer_count',
                        'count': len(viewers)
                    }))
                except:
                    pass
                    
        if websocket == td_connection:
            td_connection = None
            print('TouchDesigner disconnected')

async def main():
    port = int(os.environ.get('PORT', 8080))
    async with websockets.serve(handler, '0.0.0.0', port):
        print(f'WebSocket server running on port {port}')
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())