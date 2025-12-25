import asyncio
import websockets
import json
import os
import time

td_connection = None
viewers = {}  # {websocket: {'started': timestamp, 'active': bool}}

VIEWER_TIMEOUT = 60  # 60 секунд просмотра

async def handler(websocket, path):
    global td_connection
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data['type'] == 'td-sender':
                td_connection = websocket
                print('TouchDesigner connected')
                await websocket.send(json.dumps({
                    'type': 'viewer_count',
                    'count': sum(1 for v in viewers.values() if v['active'])
                }))
                
            elif data['type'] == 'viewer_start':
                # Запускаем или перезапускаем viewer
                viewers[websocket] = {
                    'started': time.time(),
                    'active': True
                }
                print(f'Viewer started. Total active: {sum(1 for v in viewers.values() if v["active"])}')
                
                # Уведомляем TD
                if td_connection:
                    try:
                        await td_connection.send(json.dumps({
                            'type': 'viewer_count',
                            'count': sum(1 for v in viewers.values() if v['active'])
                        }))
                    except:
                        pass
                
                # Отправляем клиенту подтверждение
                await websocket.send(json.dumps({
                    'type': 'streaming_started',
                    'duration': VIEWER_TIMEOUT
                }))
                        
            elif data['type'] == 'heartbeat':
                # Обновляем heartbeat
                if websocket in viewers:
                    viewers[websocket]['last_heartbeat'] = time.time()
                
            elif data['type'] == 'frame' and websocket == td_connection:
                # Отправляем только активным viewers
                if viewers:
                    dead_viewers = []
                    for viewer, info in list(viewers.items()):
                        if info['active']:
                            try:
                                await viewer.send(message)
                            except:
                                dead_viewers.append(viewer)
                    
                    # Удаляем мертвые viewers
                    for dead in dead_viewers:
                        if dead in viewers:
                            del viewers[dead]
                    
                    if dead_viewers and td_connection:
                        try:
                            await td_connection.send(json.dumps({
                                'type': 'viewer_count',
                                'count': sum(1 for v in viewers.values() if v['active'])
                            }))
                        except:
                            pass
                    
    except websockets.exceptions.ConnectionClosed:
        if websocket in viewers:
            del viewers[websocket]
            print(f'Viewer disconnected. Total: {len(viewers)}')
            
            if td_connection:
                try:
                    await td_connection.send(json.dumps({
                        'type': 'viewer_count',
                        'count': sum(1 for v in viewers.values() if v['active'])
                    }))
                except:
                    pass
                    
        if websocket == td_connection:
            td_connection = None
            print('TouchDesigner disconnected')

# Фоновая задача для проверки таймаутов
async def check_viewer_timeouts():
    global td_connection
    while True:
        await asyncio.sleep(2)  # Проверяем каждые 2 секунды
        
        current_time = time.time()
        expired_viewers = []
        
        for viewer, info in list(viewers.items()):
            if info['active'] and (current_time - info['started']) > VIEWER_TIMEOUT:
                expired_viewers.append(viewer)
        
        if expired_viewers:
            for viewer in expired_viewers:
                if viewer in viewers:
                    viewers[viewer]['active'] = False
                    print(f'Viewer time expired. Active: {sum(1 for v in viewers.values() if v["active"])}')
                    
                    # Уведомляем viewer что время вышло
                    try:
                        await viewer.send(json.dumps({
                            'type': 'time_expired'
                        }))
                    except:
                        pass
            
            # Уведомляем TD
            if td_connection:
                try:
                    await td_connection.send(json.dumps({
                        'type': 'viewer_count',
                        'count': sum(1 for v in viewers.values() if v['active'])
                    }))
                except:
                    pass

async def main():
    port = int(os.environ.get('PORT', 8080))
    
    # Запускаем проверку таймаутов
    timeout_task = asyncio.create_task(check_viewer_timeouts())
    
    async with websockets.serve(handler, '0.0.0.0', port):
        print(f'WebSocket server running on port {port}')
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
