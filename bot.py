import logging
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os
import google.generativeai as genai
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler
)

# Cargar variables de entorno
load_dotenv()

# Configuración básica
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configura API de Gemini
genai.configure(
    api_key=os.getenv('GEMINI_API_KEY'),
    client_options={
        'api_endpoint': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent'
    }
)

# Estados de la conversación
(
    NOMBRE, APELLIDOS, EDAD, SEXO, NIVEL_ACADEMICO, 
    RESIDENCIA, EMAIL, INFO_SISMOS, CONSULTA_IA, 
    EVALUACION_RIESGO, FINAL
) = range(11)

# ========== FUNCIONES DE BASE DE DATOS ==========
def init_db():
    conn = sqlite3.connect('sismos_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        apellidos TEXT NOT NULL,
        edad INTEGER NOT NULL,
        sexo TEXT NOT NULL,
        nivel_academico TEXT NOT NULL,
        residencia TEXT NOT NULL,
        email TEXT,
        recibir_info TEXT NOT NULL,
        fecha_registro TEXT NOT NULL,
        UNIQUE(user_id)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS consultas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tipo_consulta TEXT NOT NULL,
        contenido TEXT NOT NULL,
        respuesta TEXT NOT NULL,
        fecha TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES usuarios(user_id)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS medios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tipo_medio TEXT NOT NULL,
        file_id TEXT NOT NULL,
        fecha TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES usuarios(user_id)
    )''')
    
    conn.commit()
    conn.close()

def save_user(user_data, user_id):
    conn = sqlite3.connect('sismos_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO usuarios (
            user_id, nombre, apellidos, edad, sexo, 
            nivel_academico, residencia, email, recibir_info, fecha_registro
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            user_data['nombre'],
            user_data['apellidos'],
            user_data['edad'],
            user_data['sexo'],
            user_data['nivel_academico'],
            user_data['residencia'],
            user_data.get('email', None),
            user_data['recibir_info'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        cursor.execute('''
        UPDATE usuarios SET
            nombre = ?, apellidos = ?, edad = ?, sexo = ?,
            nivel_academico = ?, residencia = ?, email = ?,
            recibir_info = ?, fecha_registro = ?
        WHERE user_id = ?
        ''', (
            user_data['nombre'],
            user_data['apellidos'],
            user_data['edad'],
            user_data['sexo'],
            user_data['nivel_academico'],
            user_data['residencia'],
            user_data.get('email', None),
            user_data['recibir_info'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al guardar usuario: {e}")
        return False
    finally:
        conn.close()

def save_query(user_id, query_type, content, response):
    conn = sqlite3.connect('sismos_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO consultas (
            user_id, tipo_consulta, contenido, respuesta, fecha
        ) VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            query_type,
            content,
            response,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al guardar consulta: {e}")
        return False
    finally:
        conn.close()

def save_media(user_id, media_type, file_id):
    conn = sqlite3.connect('sismos_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO medios (
            user_id, tipo_medio, file_id, fecha
        ) VALUES (?, ?, ?, ?)
        ''', (
            user_id,
            media_type,
            file_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al guardar medio: {e}")
        return False
    finally:
        conn.close()

# ========== FUNCIONES DEL BOT ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación y presenta el menú principal."""
    # Limpiar cualquier estado previo
    if update.message:
        user = update.message.from_user
    else:
        user = update.callback_query.from_user
    
    context.user_data.clear()
    logger.info(f"Usuario {user.first_name} inició la conversación.")
    
    keyboard = [
        [InlineKeyboardButton("📝 Registrarse", callback_data='registro')],
        [InlineKeyboardButton("❓ Consultar sobre sismos", callback_data='consulta_ia')],
        [InlineKeyboardButton("📍 Evaluar riesgo por ubicación", callback_data='evaluar_riesgo')],
        [InlineKeyboardButton("🚨 Consejos básicos", callback_data='consejos')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Manejar tanto mensajes como callback queries
    if update.message:
        await update.message.reply_text(
            "¡Bienvenido al Sistema Inteligente de Orientación sobre Sismos de Santiago de Cuba!\n\n"
            "Selecciona una opción:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "¡Bienvenido al Sistema Inteligente de Orientación sobre Sismos de Santiago de Cuba!\n\n"
            "Selecciona una opción:",
            reply_markup=reply_markup
        )
    
    return ConversationHandler.END

async def send_consejos_basicos(query):
    """Envía consejos básicos con opción de volver al menú."""
    consejos = """
🚨 **Consejos básicos ante sismos**:

🔷 **Antes**:
- Identifica zonas seguras en casa/trabajo
- Prepara mochila de emergencia (agua, comida, medicinas, linterna)
- Asegura muebles altos y objetos pesados
    
🔷 **Durante**:
- Mantén la calma
- Ubícate en el triángulo de vida (junto a muebles resistentes)
- Aléjate de ventanas y objetos que puedan caer
- Si estás en la calle, aléjate de edificios y postes

🔷 **Después**:
- Revisa daños estructurales antes de reingresar
- No uses elevadores
- Verifica fugas de gas o cables eléctricos
- Sigue indicaciones de Defensa Civil
"""
    keyboard = [[InlineKeyboardButton("🏠 Menú Principal", callback_data='menu')]]
    await query.edit_message_text(
        consejos, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja las opciones del menú principal."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'consulta_ia':
        await query.edit_message_text(
            "Escribe tu pregunta sobre sismos en Santiago de Cuba:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
            ])
        )
        return CONSULTA_IA
    
    elif query.data == 'evaluar_riesgo':
        await query.edit_message_text(
            "Por favor, envía tu ubicación (puedes escribirla o compartir tu ubicación):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
            ])
        )
        return EVALUACION_RIESGO
    
    elif query.data == 'consejos':
        await send_consejos_basicos(query)
        return ConversationHandler.END
    
    elif query.data == 'menu':
        await start(update, context)
        return ConversationHandler.END

    elif query.data == 'registro':
        await query.edit_message_text(
            "Por favor, ingresa tu nombre:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
            ])
        )
        return NOMBRE

# ========== FLUJO DE REGISTRO ==========
async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['nombre'] = update.message.text
    await update.message.reply_text("Gracias. Ahora ingresa tus apellidos:")
    return APELLIDOS

async def recibir_apellidos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['apellidos'] = update.message.text
    await update.message.reply_text("Por favor, ingresa tu edad:")
    return EDAD

async def recibir_edad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    try:
        edad = int(update.message.text)
        if edad <= 0 or edad > 120:
            await update.message.reply_text("Por favor ingresa una edad válida (1-120).")
            return EDAD
        user_data['edad'] = edad
    except ValueError:
        await update.message.reply_text("Por favor ingresa un número válido para la edad.")
        return EDAD
    
    reply_keyboard = [["Masculino", "Femenino", "Otro"]]
    
    await update.message.reply_text(
        "Selecciona tu sexo:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return SEXO

async def recibir_sexo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['sexo'] = update.message.text
    
    reply_keyboard = [
        ["Primaria", "Secundaria"],
        ["Preuniversitario", "Universitario"],
        ["Técnico Medio", "Otro"]
    ]
    
    await update.message.reply_text(
        "Indica tu nivel académico más alto alcanzado:",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, 
            one_time_keyboard=True
        )
    )
    return NIVEL_ACADEMICO

async def recibir_nivel_academico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['nivel_academico'] = update.message.text
    await update.message.reply_text(
        "Ingresa tu centro de residencia (municipio/localidad en Santiago de Cuba):",
        reply_markup=ReplyKeyboardRemove()
    )
    return RESIDENCIA

async def recibir_residencia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['residencia'] = update.message.text
    await update.message.reply_text(
        "¿Tienes correo electrónico? Si es así, escríbelo. Si no, escribe 'no':"
    )
    return EMAIL

async def recibir_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    email = update.message.text.lower()
    if email != 'no':
        user_data['email'] = email
    
    reply_keyboard = [["Sí", "No"]]
    await update.message.reply_text(
        "¿Deseas recibir información sobre orientaciones de la Defensa Civil "
        "antes, durante o después de un sismo en Santiago de Cuba?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return INFO_SISMOS

async def recibir_info_sismos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_data['recibir_info'] = update.message.text
    user_id = update.message.from_user.id
    
    save_user(user_data, user_id)
    
    resumen = (
        "📝 **Resumen de tus datos:**\n\n"
        f"👤 Nombre: {user_data.get('nombre', 'No proporcionado')}\n"
        f"📝 Apellidos: {user_data.get('apellidos', 'No proporcionado')}\n"
        f"🎂 Edad: {user_data.get('edad', 'No proporcionado')}\n"
        f"🚻 Sexo: {user_data.get('sexo', 'No proporcionado')}\n"
        f"🎓 Nivel académico: {user_data.get('nivel_academico', 'No proporcionado')}\n"
        f"🏠 Residencia: {user_data.get('residencia', 'No proporcionado')}\n"
        f"📧 Email: {user_data.get('email', 'No proporcionado')}\n"
        f"ℹ️ Recibir info sismos: {user_data.get('recibir_info', 'No proporcionado')}\n\n"
    )
    
    if user_data['recibir_info'] == 'Sí':
        consejos = await generar_consejos_personalizados(user_data)
        resumen += f"🔍 **Recomendaciones personalizadas:**\n{consejos}"
    
    await update.message.reply_text(resumen, parse_mode="Markdown")
    
    keyboard = [
        [InlineKeyboardButton("❓ Hacer una consulta", callback_data='consulta_ia')],
        [InlineKeyboardButton("📍 Evaluar mi riesgo", callback_data='evaluar_riesgo')],
        [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
    ]
    
    await update.message.reply_text("¿Qué más te gustaría hacer?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def generar_consejos_personalizados(datos_usuario):
    try:
        contexto = f"""Genera recomendaciones para preparación ante sismos basadas en estos datos:
        - Nombre: {datos_usuario.get('nombre', '')}
        - Edad: {datos_usuario.get('edad', '')}
        - Sexo: {datos_usuario.get('sexo', '')}
        - Residencia: {datos_usuario.get('residencia', '')}
        - Nivel académico: {datos_usuario.get('nivel_academico', '')}"""
        
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(
            contexto,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=300
            )
        )
        return response.text
    except Exception as e:
        logger.error(f"Error al generar consejos: {e}")
        return "Aquí tienes algunos consejos generales:\n- Prepara un kit de emergencia\n- Identifica zonas seguras en tu vivienda"

# ========== FUNCIONALIDADES DE IA ==========
async def consulta_ia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pregunta = update.message.text
    user_id = update.message.from_user.id
    
    try:
        pregunta = pregunta.strip()
        if not pregunta:
            await update.message.reply_text("❌ Por favor escribe una pregunta válida.")
            return CONSULTA_IA
        
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(
            f"Eres un experto en sismología en Cuba. Responde de forma clara y concisa. Pregunta: {pregunta}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=500
            )
        )
        
        respuesta = response.text
        
        if len(respuesta) > 4000:
            partes = [respuesta[i:i+4000] for i in range(0, len(respuesta), 4000)]
            for parte in partes:
                await update.message.reply_text(parte)
        else:
            await update.message.reply_text(respuesta)
        
        save_query(user_id, "consulta_ia", pregunta, respuesta)
        
    except Exception as e:
        logger.error(f"Error en consulta IA: {str(e)}")
        await update.message.reply_text("⚠️ Lo siento, hubo un error procesando tu consulta. Intenta nuevamente.")

    keyboard = [
        [InlineKeyboardButton("🔄 Nueva consulta", callback_data='consulta_ia')],
        [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
    ]
    
    await update.message.reply_text(
        "¿Qué deseas hacer ahora?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def evaluar_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ubicacion = update.message.text
    user_id = update.message.from_user.id
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(
            f"Evalúa el riesgo sísmico en Santiago de Cuba considerando: historia sísmica, tipo de construcciones y geología. Ubicación: {ubicacion}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3
            )
        )
        evaluacion = response.text
        save_query(user_id, "evaluacion_riesgo", ubicacion, evaluacion)
    except Exception as e:
        logger.error(f"Error al evaluar riesgo: {e}")
        evaluacion = "Lo siento, hubo un error al evaluar el riesgo."
    
    recomendaciones = """🔍 Recomendaciones:
- Verifica que tu vivienda cumpla con normas antisísmicas
- Conoce los puntos de reunión de tu comunidad"""
    
    await update.message.reply_text(f"📌 **Evaluación para {ubicacion}:**\n\n{evaluacion}\n\n{recomendaciones}", parse_mode="Markdown")
    
    keyboard = [
        [InlineKeyboardButton("📍 Evaluar otra ubicación", callback_data='evaluar_riesgo')],
        [InlineKeyboardButton("🏠 Menú principal", callback_data='menu')]
    ]
    await update.message.reply_text(
        "¿Qué más te gustaría hacer?",
        reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

# ========== MANEJADORES AUXILIARES ==========
async def manejar_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        save_media(user_id, "foto", file_id)
        await update.message.reply_text("✅ Imagen recibida. ¿En qué puedo ayudarte? Usa /start para opciones.")
    elif update.message.voice:
        file_id = update.message.voice.file_id
        save_media(user_id, "voz", file_id)
        await update.message.reply_text("✅ Audio recibido. Actualmente solo procesamos texto. Escribe tu consulta.")

async def manejar_texto_libre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Usa /start para acceder al menú de opciones.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Abrir Menú", callback_data='menu')]
        ])
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Operación cancelada. Usa /start para comenzar de nuevo.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

# ========== CONFIGURACIÓN PRINCIPAL ==========
def main() -> None:
    """Ejecuta el bot."""
    init_db()
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()

    # Handlers básicos
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('menu', menu_principal))
    application.add_handler(CommandHandler('cancel', cancel))

    # Handlers de conversación en orden de prioridad
    registro_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^registro$')],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            APELLIDOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_apellidos)],
            EDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_edad)],
            SEXO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_sexo)],
            NIVEL_ACADEMICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nivel_academico)],
            RESIDENCIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_residencia)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_email)],
            INFO_SISMOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_info_sismos)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    application.add_handler(registro_handler)
    
    consulta_ia_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^consulta_ia$')],
        states={
            CONSULTA_IA: [MessageHandler(filters.TEXT & ~filters.COMMAND, consulta_ia)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(consulta_ia_handler)
    
    evaluar_riesgo_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^evaluar_riesgo$')],
        states={
            EVALUACION_RIESGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, evaluar_riesgo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(evaluar_riesgo_handler)

    # Handler para botones inline (debe ir después de los ConversationHandlers)
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(registro|consulta_ia|evaluar_riesgo|consejos|menu)$'))

    # Handlers de medios y texto libre (baja prioridad)
    application.add_handler(MessageHandler(filters.PHOTO | filters.VOICE, manejar_media))
    
    # Handler de texto libre con grupo más bajo (para que no intercepte los mensajes de los ConversationHandlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto_libre), group=1)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()