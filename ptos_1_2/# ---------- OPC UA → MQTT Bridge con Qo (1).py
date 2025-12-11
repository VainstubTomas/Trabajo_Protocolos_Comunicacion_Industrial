# ---------- OPC UA → MQTT Bridge (MODO DEPURACIÓN) ----------
#
# Este script tiene logging extendido para ver por qué
# falla la conexión a MQTT.
#
# ---------------------------------------------------------------------

import os
import time
import argparse
from opcua import Client, ua
import paho.mqtt.client as mqtt
import uuid
import ssl
import logging # ¡NUEVO! Importamos el logger

# ----------------------------
# Parámetros base
# ----------------------------
OPC_URL = os.getenv("OPC_URL", "opc.tcp://localhost:4840/mi_servidor/")
TOPIC_BASE = os.getenv("TOPIC_BASE", "pci") 
PUBLISH_PERIOD = float(os.getenv("PUBLISH_PERIOD", "2.0"))
RECONNECT_PERIOD = 5.0

# --- ¡NUEVOS TÓPICOS DE ESTADO! ---
TOPIC_MODBUS_ESCLAVO = "modbus_esclavo" 
TOPIC_MODBUS_MAESTRO = "modbus_maestro" 
TOPIC_OPC_SERVER = "opc_server"         
TOPIC_OPC_CLIENTE = "opc_cliente"       

# --- ¡CONFIGURACIÓN DEL BROKER (Imitando Arduino) ---
BROKER = os.getenv("MQTT_BROKER", "j72b9212.ala.us-east-1.emqxsl.com")
PORT = int(os.getenv("MQTT_PORT", "8883")) # Puerto MQTTS
MQTT_USERNAME = "user"
MQTT_PASSWORD = "FinalPCI123" 
CA_CERT_FILE = "emqxsl-ca.crt" 
# ----------------------------------------

# ----------------------------
# QoS por variable (Sin cambios)
# ----------------------------
PUB_QOS_REG0 = int(os.getenv("PUB_QOS_REG0", "0"))
PUB_QOS_REG1 = int(os.getenv("PUB_QOS_REG1", "0"))
PUB_QOS_REG2 = int(os.getenv("PUB_QOS_REG2", "0"))
PUB_QOS_REG3 = int(os.getenv("PUB_QOS_REG3", "0"))
PUB_QOS_STATUS = 1 
# ----------------------------

# ... (Parser de CLI omitido por brevedad, no cambia) ...

# ----------------------------
# MQTT callbacks (¡MODIFICADOS!)
# ----------------------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    """Callback cuando se conecta al broker MQTT."""
    # (El código 0 significa éxito)
    if reason_code == 0:
        print(f"✅ ¡ÉXITO! Conectado a MQTT {BROKER}:{PORT} (rc=0)")
    else:
        print(f"🛑 FALLO AL CONECTAR. El broker rechazó la conexión con código: {reason_code}")
        print("Códigos comunes: 2=ID de cliente inválido, 4=Usuario/Pass inválido, 5=No autorizado")

def on_publish(client, userdata, mid, reason_code, properties):
    """Callback cuando se publica un mensaje (opcional, mantener silencioso)."""
    # print(f"-> Mensaje {mid} publicado.") # Descomenta para depuración extrema
    pass

# --- ¡NUEVO! Callback de Desconexión ---
def on_disconnect(client, userdata, flags, reason_code, properties):
    """Callback para desconexiones."""
    print(f"🛑 DESCONECTADO de MQTT. Razón: {reason_code}")
    if reason_code != 0:
        print("¡Esta desconexión no fue intencional!")
# ------------------------------------

# --- Client ID Único (Sin cambios) ---
client_id_base = "Cliente_OPC_MQTT_Modbus_QoS"
client_id_unico = f"{client_id_base}-{uuid.uuid4().hex[:6]}"
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id_unico)
# ----------------------------------------

mqtt_client.on_connect = on_connect
mqtt_client.on_publish = on_publish
mqtt_client.on_disconnect = on_disconnect # <-- ¡NUEVO!

# --- LWT (Última Voluntad) (¡MODIFICADO!) ---
mqtt_client.will_set(TOPIC_OPC_CLIENTE, payload="CRASHED", qos=PUB_QOS_STATUS, retain=True)
# --- FIN DE LWT ---

# --- CONFIGURACIÓN DE SEGURIDAD (SSL/TLS con Archivo) ---
if MQTT_USERNAME and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
try:
    mqtt_client.tls_set(
        ca_certs=CA_CERT_FILE,
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLSv1_2
    )
    print(f"Usando SSL/TLS con el certificado: {CA_CERT_FILE}")
except FileNotFoundError:
    print(f"❌ ERROR: No se encontró el archivo de certificado '{CA_CERT_FILE}'")
    exit() 
except Exception as e:
    print(f"Error al configurar SSL: {e}")
    exit() 
# --- FIN DE CONFIGURACIÓN DE SEGURIDAD ---


# --- ¡NUEVO! Activar el Logger de Paho-MQTT ---
# Esto imprimirá CADA paso de la conexión en la consola
print("--- Activando Logger de MQTT (Modo Depuración) ---")
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Nivel de detalle
mqtt_client.enable_logger(logger)
# -------------------------------------------


# --- Conexión ---
print(f"Intentando conectar a {BROKER} en puerto {PORT}...")
mqtt_client.connect_async(BROKER, PORT, keepalive=10)
# --------------------
mqtt_client.loop_start()

# ----------------------------------------------------
# Función conectar y buscar nodos (¡MODIFICADA!)
# ----------------------------------------------------
def conectar_y_buscar_nodos(client):
    """
    Intenta conectar al servidor OPC UA y encontrar los nodos
    específicos que el gateway Modbus está publicando.
    """
    try:
        client.connect()
        print(f"✅ Cliente OPC UA conectado a {OPC_URL}")

        # Informamos a MQTT que este script (Cliente OPC) está VIVO
        # (Esto solo funcionará si la conexión MQTT tuvo éxito)
        mqtt_client.publish(TOPIC_OPC_CLIENTE, "RUNNING", qos=PUB_QOS_STATUS, retain=True)
        # Asumimos que si nos conectamos al Servidor OPC, él también está vivo
        mqtt_client.publish(TOPIC_OPC_SERVER, "RUNNING", qos=PUB_QOS_STATUS, retain=True)

        objects = client.get_objects_node()
        disp = None
        for node in objects.get_children():
            if node.get_browse_name().Name == "Dispositivo1":
                disp = node
                break
        if disp is None:
            print("❌ No se encontró 'Dispositivo1' en el servidor OPC UA")
            client.disconnect()
            return None

        # Buscamos los nodos por los NOMBRES correctos
        nodes_opc = {
            # Datos
            "pot":    disp.get_child(["2:Potenciometro"]),
            "ultra":  disp.get_child(["2:Distancia_Ultrasonido"]),
            "btn1":   disp.get_child(["2:Boton_1"]),
            "btn2":   disp.get_child(["2:Boton_2"]),
            # Contadores
            "ok":     disp.get_child(["2:Modbus_Aceptadas"]),
            "crc":    disp.get_child(["2:Modbus_Error_CRC"]),
            "nr":     disp.get_child(["2:Modbus_No_Alcanzado"]),
            # ¡NUEVOS TAGS DE ESTADO!
            "esclavo": disp.get_child(["2:Modbus_Estado_Esclavo"]),
            "maestro": disp.get_child(["2:Modbus_Estado_Maestro"])
        }
        print("✅ Nodos OPC UA encontrados.")
        return nodes_opc

    except Exception as e:
        print(f"⚠️ Error al conectar o buscar nodos OPC: {e}")
        # Si la conexión falla, es porque el SERVIDOR OPC (Script 2) está caído
        mqtt_client.publish(TOPIC_OPC_SERVER, "CRASHED", qos=PUB_QOS_STATUS, retain=True)
        try:
            client.disconnect()
        except Exception:
            pass
        return None

# ----------------------------
# Bucle principal (¡MODIFICADO!)
# ----------------------------
client = Client(OPC_URL)
nodes_opc = None
print("Iniciando bridge... (Conectando a OPC UA y MQTT)")

try:
    while True:
        try:
            # 1. ESTADO: DESCONECTADO (Intentar conectar)
            if nodes_opc is None:
                # Damos tiempo a que se establezca la conexión MQTT
                # antes de intentar la de OPC
                if not mqtt_client.is_connected():
                    print("Esperando conexión MQTT...")
                    time.sleep(1.0)
                    continue # Volvemos al inicio del bucle
                
                print("Conexión MQTT establecida. Intentando conectar a OPC UA...")
                nodes_opc = conectar_y_buscar_nodos(client)
                
                if nodes_opc is None:
                    # El error ya fue publicado dentro de conectar_y_buscar_nodos()
                    print(f"Reintento de conexión OPC en {RECONNECT_PERIOD}s...")
                    time.sleep(RECONNECT_PERIOD)
                    continue
            
            # 2. ESTADO: CONECTADO (Leer y publicar)
            
            # --- ¡LECTURA DE DATOS! ---
            pot_val = nodes_opc["pot"].get_value()
            ultra_val = nodes_opc["ultra"].get_value()
            btn1_val = nodes_opc["btn1"].get_value()
            btn2_val = nodes_opc["btn2"].get_value()
            ok_val   = nodes_opc["ok"].get_value()
            crc_val  = nodes_opc["crc"].get_value()
            nr_val   = nodes_opc["nr"].get_value()
            esclavo_status_val = nodes_opc["esclavo"].get_value()
            maestro_status_val = nodes_opc["maestro"].get_value()


            # --- ¡PUBLICACIÓN MQTT! ---
            # (Tópicos de datos y contadores omitidos por brevedad, no cambian)
            mqtt_client.publish(f"{TOPIC_BASE}/sensor/pot", pot_val, qos=PUB_QOS_REG0)
            mqtt_client.publish(f"{TOPIC_BASE}/sensor/distancia", ultra_val, qos=PUB_QOS_REG1)
            mqtt_client.publish(f"{TOPIC_BASE}/datos/boton_1", btn1_val, qos=PUB_QOS_REG2)
            mqtt_client.publish(f"{TOPIC_BASE}/datos/boton_2", btn2_val, qos=PUB_QOS_REG3)
            mqtt_client.publish(f"{TOPIC_BASE}/estadistica/modbus_aceptadas", ok_val, qos=PUB_QOS_STATUS)
            mqtt_client.publish(f"{TOPIC_BASE}/estadistica/modbus_crc_error", crc_val, qos=PUB_QOS_STATUS)
            mqtt_client.publish(f"{TOPIC_BASE}/estadistica/modbus_no_alcanzado", nr_val, qos=PUB_QOS_STATUS)
            
            # ¡NUEVOS TÓPICOS DE ESTADO (Raíz)!
            mqtt_client.publish(f"{TOPIC_BASE}/state/{TOPIC_MODBUS_ESCLAVO}", esclavo_status_val, qos=PUB_QOS_STATUS, retain=True)
            mqtt_client.publish(f"{TOPIC_BASE}/state/{TOPIC_MODBUS_MAESTRO}", maestro_status_val, qos=PUB_QOS_STATUS, retain=True)
            mqtt_client.publish(f"{TOPIC_BASE}/state/{TOPIC_OPC_SERVER}", "RUNNING", qos=PUB_QOS_STATUS, retain=True) # Heartbeat
            mqtt_client.publish(f"{TOPIC_BASE}/state/{TOPIC_OPC_CLIENTE}", "RUNNING", qos=PUB_QOS_STATUS, retain=True) # Heartbeat

            # Actualizamos el print
            print(f"→ Pot={pot_val} Ultra={ultra_val} | Esclavo: {esclavo_status_val} | Maestro: {maestro_status_val}")
            
            time.sleep(PUBLISH_PERIOD)

        except Exception as e:
            if isinstance(e, KeyboardInterrupt):
                raise e

            # --- ¡MANEJO DE CAÍDA DEL SERVIDOR OPC (Script 2)! ---
            print(f"\n🛑 ERROR (¿Conexión OPC perdida?): {e}")
            print("Publicando estado 'CRASHED' para OPC_SERVER y reintentando...")
            
            mqtt_client.publish(TOPIC_OPC_SERVER, "CRASHED", qos=PUB_QOS_STATUS, retain=True)

            nodes_opc = None
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(RECONNECT_PERIOD)

except KeyboardInterrupt:
    print("\n🛑 Deteniendo cliente OPC UA y MQTT (Ctrl+C)...")
finally:
    # --- MANEJO DE SALIDA LIMPIA (MEJORADO) ---
    print("Iniciando secuencia de apagado limpio...")
    try:
        # Limpiamos los estados de los scripts de PC
        print("Limpiando estados retenidos de OPC_CLIENTE y OPC_SERVER...")
        msg_info_cli = mqtt_client.publish(TOPIC_OPC_CLIENTE, "", qos=PUB_QOS_STATUS, retain=True)
        msg_info_srv = mqtt_client.publish(TOPIC_OPC_SERVER, "", qos=PUB_QOS_STATUS, retain=True)
        
        msg_info_cli.wait_for_publish(timeout=2.0) 
        msg_info_srv.wait_for_publish(timeout=2.0)
        print("Mensajes 'limpios' publicados.")
        
        # Detenemos todo
        print("Deteniendo bucle MQTT...")
        mqtt_client.loop_stop()
        print("Desconectando MQTT...")
        mqtt_client.disconnect() 
        print("Desconectando OPC...")
        client.disconnect()
        print("✅ Desconectado correctamente")

    except KeyboardInterrupt:
        print("\n... (Cierre forzado durante la limpieza) ...")
        pass 
    except Exception as e:
        print(f"Error durante la limpieza: {e}")
        pass