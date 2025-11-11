import express from 'express';
import webController from '../controllers/webController.js';

const viewsRouter = express.Router();

//endpoints
viewsRouter.get('/', webController.renderHomePage);

export default viewsRouter;