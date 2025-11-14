import mqtt from 'mqtt';
import fs from 'fs';

//Broker Configuration
const BROKER_URL = 'j72b9212.ala.us-east-1.emqxsl.com';
const BROKER_PORT = 8883;
const MQTT_BROKER_URL = `mqtts://${BROKER_URL}:${BROKER_PORT}`;

//certificacion de autoridad del broker
const CA_CERT = fs.readFileSync('./emqxsl-ca.crt');

//MQTT client
let client = null;

//topics
//wildcard '#' porque todos los topicos comienzan con pci/
const TOPIC_STATUS_BASE = 'pci/#';
const TOPIC_CMD_ANALOG = 'pci/value1/analog'; // Luminosidad (0-255)
const TOPIC_CMD_DIGITAL = 'pci/value1/dig';   //ON / OFF

/**
 * socket.io objeto from app.js to listen events in live
 * @param {object} io
 */

function init(io) {
    if (client) return; 

    client = mqtt.connect(MQTT_BROKER_URL, {
        username:'user',
        password:'FinalPCI123',
        //clean para recordar usuario cuando se desconecte
        clean: true,
        //credencial
        ca:CA_CERT
    });

    // 1. Drive connection
    client.on('connect', () => {
        console.log('Cliente MQTT conectado al broker.');
        
        // sub to topic base
        client.subscribe(TOPIC_STATUS_BASE, (err) => {
            if (err) {
                console.error('Error al suscribirse a tópicos:', err);
            } else {
                console.log(`Suscrito a la base de tópicos: ${TOPIC_STATUS_BASE}`);
            }
        });
    });

    //estados protocolos

    //Estado mqtt
    client.on('error', (err) => {
        console.error('Error en el cliente MQTT:', err.message);
        console.log('INTENTANDO EMITIR FALLO AL CLIENTE WEB');
        if (io) {
            io.emit('system_fault', { source: 'MQTT_BROKER', message: 'Conexión perdida con el Broker' });
        }
    });

    // 2. Messages reception (GATEWAY MQTT -> Socket.io)
    client.on('message', (topic, message) => {
        try {
            const payload = message.toString();
            
            // Log of receipted data
            console.log(`[MQTT_RECIBIDO] Tópico: ${topic}, Payload: ${payload}`);

            // io propagation - send to all web connected clients
            if (io) {
                io.emit('mqtt_update', { topic, payload });
            }

        } catch (e) {
            console.error('Error al procesar mensaje MQTT:', e);
        }
    });
}

/**
 * Publica un comando de control en el tópico MQTT.
 * @param {string} type - 'analogico' o 'digital'
 * @param {string} payload - El valor del comando (ej: '150' o '1').
 */
function publishCommand(type, payload) {
    if (!client || !client.connected) {
        console.error('No se puede publicar: Cliente MQTT no está conectado.');
        return false;
    }

    let topic;
    // Seleccionar el tópico de destino basado en el tipo de comando
    switch (type) {
        case 'analog':
            topic = TOPIC_CMD_ANALOG;
            break;
        case 'digital':
            topic = TOPIC_CMD_DIGITAL;
            break;
        default:
            console.error(`Tipo de comando desconocido: ${type}`);
            return false;
    }

    // Publicar el payload en el tópico seleccionado
    client.publish(topic, String(payload), { qos: 0, retain: false }, (err) => {
        if (err) {
            console.error(`Error al publicar en ${topic}:`, err);
        } else {
            console.log(`Comando publicado: ${topic} -> ${payload}`);
        }
    });
    return true;
}


// --- KEY FUNCTIONS EXPORT ---
export default {
    init,
    publishCommand,
};