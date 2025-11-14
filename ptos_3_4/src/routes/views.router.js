import express from 'express';
import webController from '../controllers/webController.js';

const viewsRouter = express.Router();

//endpoints
viewsRouter.get('/', webController.renderHomePage);
//para recibir valores analogicos
viewsRouter.post('/command/analog', webController.handleAnalogCommand);
//para recibir valores digitales
viewsRouter.post('/command/digital', webController.handleDigitalCommand);

export default viewsRouter;