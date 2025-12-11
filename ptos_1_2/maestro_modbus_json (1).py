import serial
import time
import struct
import threading
import json
import os
import paho.mqtt.client as mqtt
import ssl
import uuid

# --- 1.d) Configuración MODBUS (Lectura) ---
PUERTO_SERIAL = "COM7"
BAUD_RATE = 9600
PARITY = serial.PARITY_NONE
STOP_BITS = serial.STOPBITS_ONE
BYTE_SIZE = serial.EIGHTBITS
TIMEOUT_ESPERA = 1.0

ID_ESCLAVO = 1
FUNCION_LEER_REGISTROS = 0x03
REGISTRO_INICIO = 0
CANTIDAD_REGISTROS = 4

# --- Configuración MODBUS (Escritura) ---
FUNCION_ESCRIBIR_COIL = 0x05     # Escribir 1 bit (digital 0/1)
FUNCION_ESCRIBIR_REGISTRO = 0x06 # Escribir 16 bits (analógico 0-255)
COIL_LED_DIGITAL = 0             # Bobina para el LED digital
REGISTRO_LED_ANALOG = 4          # Registro para el LED analógico

# --- 2.a) Configuración de Archivo JSON ---
JSON_FILE = "datos_modbus.json"
JSON_TMP_FILE = "datos_modbus.tmp"

# --- 3. Configuración de MQTT ---
TOPIC_BASE = "pci"
BROKER = "j72b9212.ala.us-east-1.emqxsl.com"
PORT = 8883
MQTT_USERNAME = "user"
MQTT_PASSWORD = "FinalPCI123"
CA_CERT_FILE = "emqxsl-ca.crt"

# Tópicos a los que este script se suscribirá
TOPICO_SUB_DIG = f"{TOPIC_BASE}/value1/dig"
TOPICO_SUB_ANALOG = f"{TOPIC_BASE}/value1/analog"

# --- Globales ---
stats_lock = threading.Lock()
stats = {
    'aceptadas': 0,
    'error_crc': 0,
    'no_alcanzado': 0,
    'excepcion_esclavo': 0
}
ser = None 
serial_lock = threading.Lock()

# --- Funciones CRC ---
def calcular_crc(trama_bytes):
    crc_registro = 0xFFFF
    polinomio = 0xA001
    for byte in trama_bytes:
        crc_registro ^= byte
        for _ in range(8):
            if crc_registro & 0x0001:
                crc_registro = (crc_registro >> 1) ^ polinomio
            else:
                crc_registro = crc_registro >> 1
    return struct.pack('<H', crc_registro)

def verificar_crc(trama_completa):
    if len(trama_completa) < 4:
        return False
    trama_datos = trama_completa[:-2]
    crc_recibido = trama_completa[-2:]
    crc_calculado = calcular_crc(trama_datos)
    return crc_recibido == crc_calculado

# --- Bucle Maestro MODBUS (Lectura) ---
def ciclo_maestro_modbus(ser_local):
    pdu = struct.pack('>HH', REGISTRO_INICIO, CANTIDAD_REGISTROS)
    trama_sin_crc = struct.pack('BB', ID_ESCLAVO, FUNCION_LEER_REGISTROS) + pdu
    crc = calcular_crc(trama_sin_crc)
    trama_completa = trama_sin_crc + crc

    try:
        ser_local.reset_input_buffer()
        ser_local.reset_output_buffer()
        ser_local.write(trama_completa)
        
        inicio_respuesta = ser_local.read(3)
        # Validamos que hayamos recibido al menos 3 bytes
        if len(inicio_respuesta) < 3:
            # Si no recibimos nada o recibimos basura incompleta
            # No contamos esto como "no alcanzado" inmediatamente para no spamear logs,
            # pero retornamos error para que el bucle reintente.
            return ("ERROR_TRAMA_INCOMPLETA", None)

        if inicio_respuesta[1] == (FUNCION_LEER_REGISTROS + 0x80):
            # ... (Manejo de excepción esclavo) ...
            with stats_lock:
                stats['excepcion_esclavo'] += 1
            ser_local.read(2) 
            return ("ERROR_ESCLAVO", None) 

        conteo_bytes = inicio_respuesta[2]
        resto_respuesta = ser_local.read(conteo_bytes + 2)
        respuesta = inicio_respuesta + resto_respuesta

        if verificar_crc(respuesta):
            with stats_lock:
                stats['aceptadas'] += 1
            
            datos_payload = respuesta[3:-2]
            registros = []
            for i in range(0, len(datos_payload), 2):
                registro = struct.unpack('>H', datos_payload[i:i+2])[0]
                registros.append(registro)
            
            print(f"ESTADO: ACEPTADA. Datos: {registros}")
            return ("OK", registros)
        else:
            print("ESTADO: CRC ERROR")
            with stats_lock:
                stats['error_crc'] += 1
            return ("ERROR_CRC", None)

    except (serial.SerialException, OSError) as e:
        raise e 
    
    except Exception as e:
        print(f"Error inesperado DENTRO del ciclo: {e}")
        return ("ERROR_INTERNO", None)

# --- Función de escritura atómica ---
def escribir_json_seguro(datos):
    try:
        with open(JSON_TMP_FILE, 'w') as f:
            json.dump(datos, f, indent=4)
        os.replace(JSON_TMP_FILE, JSON_FILE)
    except Exception as e:
        print(f"ERROR: No se pudo escribir en el archivo JSON: {e}")

# --- Callbacks de MQTT ---
def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"✅ Conectado a MQTT {BROKER}:{PORT} (rc={reason_code})")
    client.subscribe(TOPICO_SUB_DIG)
    client.subscribe(TOPICO_SUB_ANALOG)
    print(f"Suscrito a {TOPICO_SUB_DIG}")
    print(f"Suscrito a {TOPICO_SUB_ANALOG}")

def on_message(client, userdata, msg):
    """Callback cuando llega un mensaje de MQTT (Control)."""
    global ser 
    global serial_lock 

    if ser is None or not ser.is_open:
        return

    payload = msg.payload.decode('utf-8')
    print(f"\n--- [MQTT RECIBIDO] Tópico: {msg.topic}, Payload: {payload} ---")

    try:
        trama_sin_crc = None
        if msg.topic == TOPICO_SUB_DIG:
            valor = int(payload)
            if valor == 1:
                payload_modbus = 0xFF00 # ON
                print("Comando: ENCENDER LED Digital")
            else:
                payload_modbus = 0x0000 # OFF
                print("Comando: APAGAR LED Digital")
            
            pdu = struct.pack('>HH', COIL_LED_DIGITAL, payload_modbus)
            trama_sin_crc = struct.pack('BB', ID_ESCLAVO, FUNCION_ESCRIBIR_COIL) + pdu

        elif msg.topic == TOPICO_SUB_ANALOG:
            valor = int(payload)
            if not 0 <= valor <= 255: 
                return
            print(f"Comando: AJUSTAR LED Analógico a {valor}")
            pdu = struct.pack('>HH', REGISTRO_LED_ANALOG, valor)
            trama_sin_crc = struct.pack('BB', ID_ESCLAVO, FUNCION_ESCRIBIR_REGISTRO) + pdu
        
        else:
            return 

        if trama_sin_crc:
            crc = calcular_crc(trama_sin_crc)
            trama_completa = trama_sin_crc + crc

            # --- ¡CAMBIO CLAVE! ---
            # Enviamos y NO esperamos respuesta.
            # Esto evita el bloqueo (deadlock) y el error de eco.
            with serial_lock:
                print(f"Enviando comando: {trama_completa.hex()}")
                ser.write(trama_completa) 
                # Eliminamos ser.read() aquí.
                print("Comando enviado.") 

    except Exception as e:
        print(f"Error en on_message: {e}")

# --- Bucle Principal ---
if __name__ == "__main__":
    
    client_id_unico = f"maestro-modbus-{uuid.uuid4().hex[:6]}"
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id_unico)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message 
    
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

    mqtt_client.connect_async(BROKER, PORT, keepalive=60)
    mqtt_client.loop_start() 
    
    try:
        while True: 
            try:
                ser = serial.Serial(
                    port=PUERTO_SERIAL,
                    baudrate=BAUD_RATE,
                    parity=PARITY,
                    stopbits=STOP_BITS,
                    bytesize=BYTE_SIZE,
                    timeout=TIMEOUT_ESPERA
                )
                    
                print(f"Maestro MODBUS (Serial simple) iniciado en {PUERTO_SERIAL}")
                escribir_json_seguro({"estado": "INICIANDO", "timestamp_lectura": int(time.time())}) 
                
                while True: 
                    
                    with serial_lock:
                        (estado, datos_leidos) = ciclo_maestro_modbus(ser)
                    
                    datos_para_json = {
                        "estado": estado,
                        "timestamp_lectura": int(time.time())
                    }
                    
                    if estado == "OK":
                        datos_para_json["potenciometro"] = datos_leidos[0]
                        datos_para_json["ultrasonido"] = datos_leidos[1]
                        datos_para_json["boton_1"] = datos_leidos[2]
                        datos_para_json["boton_2"] = datos_leidos[3]
                    
                    with stats_lock:
                        datos_para_json["stats_aceptadas"] = stats['aceptadas']
                        datos_para_json["stats_crc"] = stats['error_crc']
                        datos_para_json["stats_no_alcanzado"] = stats['no_alcanzado']
                        
                        print(f"Stats -> A: {stats['aceptadas']} | CRC: {stats['error_crc']} | NR: {stats['no_alcanzado']} | Estado: {estado}")
                    
                    escribir_json_seguro(datos_para_json)

                    time.sleep(2) 

            except (serial.SerialException, OSError) as e:
                print(f"ESTADO: ERROR SERIAL (Desconexión). {e}")
                print("Reintentando conexión en 5 segundos...")
                
                if ser and ser.is_open:
                    ser.close()
                ser = None 
                
                with stats_lock:
                    stats['no_alcanzado'] += 1
                    datos_error = {
                        "estado": "ERROR_DESCONECTADO",
                        "timestamp_lectura": int(time.time()),
                        "stats_no_alcanzado": stats['no_alcanzado']
                    }
                escribir_json_seguro(datos_error)
                    
                time.sleep(5) 
                
    except KeyboardInterrupt:
        print("Cerrando script Modbus y MQTT...")
        
    finally:
        if ser and ser.is_open:
            ser.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        escribir_json_seguro({"estado": "DETENIDO", "timestamp_lectura": int(time.time())})
        print("Estado 'DETENIDO' escrito en JSON.")