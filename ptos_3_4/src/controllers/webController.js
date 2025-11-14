import mqttClient from "../config/mqttClient.js";

/**
 * Maneja el comando de luminosidad (analógico).
 * @param {object} req - Petición HTTP.
 * @param {object} res - Respuesta HTTP.
 */
const handleAnalogCommand = (req, res) => {
    try {
        const { value } = req.body; // Esperamos del cliente
        
        // 1. Validación simple
        if (value === undefined) {
            return res.status(400).json({ message: "Falta el valor analógico." });
        }

        // 2. Publicar el comando a través de MQTT
        const success = mqttClient.publishCommand('analog', value);

        if (success) {
            return res.status(200).json({ status: 'success', message: `Comando analógico ${value} enviado.` });
        } else {
            return res.status(503).json({ status: 'error', message: 'Servidor MQTT no conectado.' });
        }
    } catch (error) {
        return res.status(500).json({ message: error.message });
    }
};


/**
 * Maneja el comando digital (LED ON/OFF).
 * @param {object} req - Petición HTTP.
 * @param {object} res - Respuesta HTTP.
 */
const handleDigitalCommand = (req, res) => {
    try {
        const { state } = req.body; // Esperamos { state: "1" } o { state: "0" }
        
        if (state === undefined) {
            return res.status(400).json({ message: "Falta el estado digital." });
        }

        // 2. Publicar el comando a través de MQTT
        const success = mqttClient.publishCommand('digital', state);

        if (success) {
            return res.status(200).json({ status: 'success', message: `Comando digital ${state} enviado.` });
        } else {
            return res.status(503).json({ status: 'error', message: 'Servidor MQTT no conectado.' });
        }
    } catch (error) {
        return res.status(500).json({ message: error.message });
    }
};

/**
 * Renderiza la página de inicio (Panel de Control).
 * @param {object} req - Objeto de solicitud de Express.
 * @param {object} res - Objeto de respuesta de Express.
 */
const renderHomePage = (req, res) => {
    res.render('index');
};

// export function
export default {
    renderHomePage,
    handleAnalogCommand,
    handleDigitalCommand,
};