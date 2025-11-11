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
    // export others functions.
};