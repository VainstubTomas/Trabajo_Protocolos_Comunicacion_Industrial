import time
import json
import os
from opcua import Server, ua

# --- 1. Configuración ---
JSON_FILE = "datos_modbus.json" # El archivo que escribe el maestro Modbus
POLL_INTERVAL = 1.0 # Cada cuánto leemos el archivo JSON (en segundos)
JSON_TIMEOUT_SECS = 10.0 # Segundos para detectar un crash del Maestro Modbus

def iniciar_servidor_opcua():
    """
    Configura e inicia el servidor OPC UA.
    Retorna el servidor y un diccionario con los nodos.
    """
    servidor = Server()
    
    url_servidor = "opc.tcp://0.0.0.0:4840/mi_servidor/"
    servidor.set_endpoint(url_servidor)
    
    nombre_ns = "Servidor_MODBUS_Gateway"
    idx = servidor.register_namespace(nombre_ns)
    
    objetos = servidor.get_objects_node()
    mi_dispositivo = objetos.add_object(idx, "Dispositivo1")
    
    # --- Creación de Nodos OPC UA ---
    opc_potenciometro = mi_dispositivo.add_variable(idx, "Potenciometro", 0)
    opc_ultrasonido = mi_dispositivo.add_variable(idx, "Distancia_Ultrasonido", 0)
    opc_boton_1 = mi_dispositivo.add_variable(idx, "Boton_1", 0)
    opc_boton_2 = mi_dispositivo.add_variable(idx, "Boton_2", 0)
    
    opc_modbus_aceptadas = mi_dispositivo.add_variable(idx, "Modbus_Aceptadas", 0)
    opc_modbus_error_crc = mi_dispositivo.add_variable(idx, "Modbus_Error_CRC", 0)
    opc_modbus_no_alcanzado = mi_dispositivo.add_variable(idx, "Modbus_No_Alcanzado", 0)
    
    # --- ¡CAMBIOS AQUÍ! Dos tags de estado separados ---
    opc_modbus_estado_esclavo = mi_dispositivo.add_variable(idx, "Modbus_Estado_Esclavo", "INICIANDO")
    opc_modbus_estado_maestro = mi_dispositivo.add_variable(idx, "Modbus_Estado_Maestro", "INICIANDO")
    # ------------------------------------------------
    
    nodos_lista = [opc_potenciometro, opc_ultrasonido, opc_boton_1, opc_boton_2, 
                   opc_modbus_aceptadas, opc_modbus_error_crc, 
                   opc_modbus_no_alcanzado, 
                   opc_modbus_estado_esclavo, # <-- Añadido
                   opc_modbus_estado_maestro  # <-- Añadido
                   ]
                   
    for nodo in nodos_lista:
        nodo.set_writable(False) 
        permiso_lectura = ua.DataValue(ua.AccessLevel.CurrentRead.mask)
        nodo.set_attribute(ua.AttributeIds.UserAccessLevel, permiso_lectura)
    
    servidor.start()
    print(f"--- Servidor OPC UA iniciado en {url_servidor} ---")
    
    # Devolvemos un diccionario de nodos para fácil acceso
    opc_nodes = {
        "pot": opc_potenciometro,
        "ultra": opc_ultrasonido,
        "btn1": opc_boton_1,
        "btn2": opc_boton_2,
        "ok": opc_modbus_aceptadas,
        "crc": opc_modbus_error_crc,
        "nr": opc_modbus_no_alcanzado,
        "esclavo": opc_modbus_estado_esclavo, # <-- Nuevo
        "maestro": opc_modbus_estado_maestro  # <-- Nuevo
    }
    
    return servidor, opc_nodes

# --- Bucle Principal (Lee JSON y actualiza OPC) ---
if __name__ == "__main__":
    
    servidor_opc, opc_nodes = iniciar_servidor_opcua()
    
    estado_maestro_cache = "" # Cache para el estado del maestro
    estado_esclavo_cache = "" # Cache para el estado del esclavo
    
    try:
        while True:
            ahora = int(time.time()) # Tomamos la hora actual
            estado_maestro_actual = ""
            estado_esclavo_actual = ""
            
            try:
                # 1. Intentar leer el archivo JSON
                with open(JSON_FILE, 'r') as f:
                    datos = json.load(f)
                
                # --- INICIO DEL CAMBIO: Lógica de Vigilante ---
                
                # 2. Comprobar la "frescura" de los datos (Estado del Maestro)
                timestamp_json = datos.get("timestamp_lectura", 0)
                json_es_viejo = (ahora - timestamp_json) > JSON_TIMEOUT_SECS
                
                estado_esclavo_json = datos.get("estado", "DESCONOCIDO")

                if json_es_viejo:
                    # ¡El Script 1 (Modbus Maestro) se ha caído!
                    if estado_esclavo_json == "DETENIDO":
                        estado_maestro_actual = "DETENIDO"
                    else:
                        estado_maestro_actual = "CRASHED"
                else:
                    # El Script 1 está vivo
                    estado_maestro_actual = "RUNNING"

                # 3. Obtener el estado del Esclavo Modbus (Hardware)
                estado_esclavo_actual = estado_esclavo_json
                
                # 4. Actualizar tags OPC solo si hay cambios
                if estado_maestro_actual != estado_maestro_cache:
                    opc_nodes["maestro"].set_value(estado_maestro_actual)
                    estado_maestro_cache = estado_maestro_actual
                    print(f"Estado Maestro Modbus (Script 1) -> {estado_maestro_actual}")

                if estado_esclavo_actual != estado_esclavo_cache:
                    opc_nodes["esclavo"].set_value(estado_esclavo_actual)
                    estado_esclavo_cache = estado_esclavo_actual
                    print(f"Estado Esclavo Modbus (Hardware) -> {estado_esclavo_actual}")

                # 5. Actualizar datos (solo si el esclavo está OK)
                if estado_esclavo_actual == "OK":
                    opc_nodes["pot"].set_value(datos.get("potenciometro", 0))
                    opc_nodes["ultra"].set_value(datos.get("ultrasonido", 0))
                    opc_nodes["btn1"].set_value(datos.get("boton_1", 0))
                    opc_nodes["btn2"].set_value(datos.get("boton_2", 0))
                    opc_nodes["ok"].set_value(datos.get("stats_aceptadas", 0))
                    opc_nodes["crc"].set_value(datos.get("stats_crc", 0))
                    opc_nodes["nr"].set_value(datos.get("stats_no_alcanzado", 0))
                
                # --- FIN DEL CAMBIO ---
                
            except FileNotFoundError:
                estado_maestro_actual = "NO_INICIADO"
                if estado_maestro_cache != estado_maestro_actual:
                    print(f"Esperando a que {JSON_FILE} sea creado por el script Modbus...")
                    opc_nodes["maestro"].set_value(estado_maestro_actual)
                    opc_nodes["esclavo"].set_value(estado_maestro_actual)
                    estado_maestro_cache = estado_maestro_actual
                    estado_esclavo_cache = estado_maestro_actual

            except (json.JSONDecodeError, PermissionError):
                print("Error leyendo JSON (probablemente en escritura), reintentando...")
            except Exception as e:
                print(f"Error inesperado leyendo JSON: {e}")
            
            time.sleep(POLL_INTERVAL) # Esperamos antes de la siguiente lectura
                
    except KeyboardInterrupt:
        print("Cerrando servidor OPC UA...")
        servidor_opc.stop()