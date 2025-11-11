import express from 'express';
import http from 'http';
import {engine} from 'express-handlebars';
import {Server} from 'socket.io';
import viewsRouter from './routes/views.router.js';
import mqttClient from './config/mqttClient.js';

const app = express();
const server = http.createServer(app);
const io = new Server(server); //io = input/output

//statics
app.use(express.static("public"));

//handlebars config
app.engine("handlebars", engine());
app.set("view engine", "handlebars");
app.set("views","./src/views");

//websocket (io) config
io.on("connection", (socket)=>{
    console.log("Nuevo cliente conectado " + socket.id);
})

//mqtt initialisation
mqttClient.init(io);

//endpoints
app.use("/", viewsRouter);

//server initialisation
server.listen(8080, ()=>{
    console.log("Server initialisated sussefully");
})