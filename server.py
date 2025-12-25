import asyncio
import websockets
import json
import os

td_connection = None
viewers = {}  # Теперь словарь с timestamp последнего heartbeat

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
                viewers[websocket] = asyncio.get_event_loop().time()
                print(f'Viewer connected. Total: {len(viewers)}')
                
                # Уведомляем TD что появился viewer
                if td_connection:
                    try:
                        await td_connection.send(json.dumps({
                            'type': 'viewer_count',
                            'count': len(viewers)
                        }))
                    except:
                        pass
                        
            elif data['type'] == 'heartbeat':
                # Обновляем timestamp viewer
                if websocket in viewers:
                    viewers[websocket] = asyncio.get_event_loop().time()
                
            elif data['type'] == 'frame' and websocket == td_connection:
                # Отправляем только если есть viewers
                if viewers:
                    dead_viewers = set()
                    for viewer in list(viewers.keys()):
                        try:
                            await viewer.send(message)
                        except:
                            dead_viewers.add(viewer)
                    
                    # Удаляем мертвые viewers
                    for dead in dead_viewers:
                        if dead in viewers:
                            del viewers[dead]
                            print(f'Viewer died. Total: {len(viewers)}')
                    
                    # Уведомляем TD если изменилось количество
                    if dead_viewers and td_connection:
                        try:
                            await td_connection.send(json.dumps({
                                'type': 'viewer_count',
                                'count': len(viewers)
                            }))
                        except:
                            pass
                    
    except websockets.exceptions.ConnectionClosed:
        if websocket in viewers:
            del viewers[websocket]
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

# Фоновая задача для очистки мертвых viewers
async def cleanup_dead_viewers():
    global td_connection
    while True:
        await asyncio.sleep(5)  # Проверяем каждые 5 секунд
        
        current_time = asyncio.get_event_loop().time()
        dead_viewers = []
        
        for viewer, last_seen in list(viewers.items()):
            # Если viewer не откликался 10 секунд - считаем мертвым
            if current_time - last_seen > 10:
                dead_viewers.append(viewer)
        
        if dead_viewers:
            for dead in dead_viewers:
                if dead in viewers:
                    del viewers[dead]
                    print(f'Viewer timeout. Total: {len(viewers)}')
            
            # Уведомляем TD
            if td_connection:
                try:
                    await td_connection.send(json.dumps({
                        'type': 'viewer_count',
                        'count': len(viewers)
                    }))
                except:
                    pass

async def main():
    port = int(os.environ.get('PORT', 8080))
    
    # Запускаем cleanup в фоне
    cleanup_task = asyncio.create_task(cleanup_dead_viewers())
    
    async with websockets.serve(handler, '0.0.0.0', port):
        print(f'WebSocket server running on port {port}')
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
