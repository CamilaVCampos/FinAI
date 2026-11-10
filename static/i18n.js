// FinAI translations. Add a language by copying the "en" block and translating every value.
// {name} placeholders are filled in by t(key, {name: value}).
const STRINGS = {
  en: {
    "tab.home": "Home", "tab.spending": "Spending", "tab.goals": "Goals", "tab.bills": "Bills", "tab.profile": "Profile",
    "badge.paypal": "PayPal {env}", "badge.paypal_off": "PayPal not connected", "badge.ai": "Claude AI", "badge.ai_off": "AI off",
    "loading.default": "Loading your finances...", "loading.settings": "Applying your settings. Claude is rewriting your analysis...",
    "loading.refresh": "Claude is re-analyzing your spending...",

    "home.hello": "Your financial overview", "home.left": "Money left in {month}", "home.left_over": "Overspent in {month}",
    "home.of_income": "Spent {spent} of {income} income", "home.score": "Health", "home.spent": "Spent",
    "home.free": "Free after bills", "home.analyzing": "Analyzing your finances...",
    "home.budget": "Your {needs} / {wants} / {savings} budget", "home.of_income_short": "of income",
    "home.target": "target {amount} · {pct}%", "home.wants_target": "target with luxury {amount} · {pct}%",
    "home.inside_wants": "counts inside wants", "home.month_saved": "saved {amount}", "home.month_over": "over by {amount}", "home.over": "Over", "home.ok": "On track", "home.under": "Below target",
    "home.months": "Month by month", "home.so_far": "(so far)", "home.saved": "+{amount} saved",
    "home.insights": "AI insights", "home.by_claude": "by Claude", "home.basic": "basic rules",
    "home.suggested": "AI suggested saving", "home.per_month": "{amount} / month",
    "home.save_toward": "Save it toward \"{goal}\"", "home.create_goal": "Create a goal",
    "home.sample_profile": "Sample profile: the {income} monthly income, the goal and the fixed payments are examples so the demo never starts empty.",
    "home.enter_income": "Enter your own income",
    "cat.need": "need", "cat.want": "want", "cat.luxury": "luxury", "cat.saving": "saving", "cat.income": "income",
    "legend.needs": "Needs", "legend.wants": "Wants", "legend.luxury": "Luxury", "legend.savings": "Savings",

    "alert.no_income": "Add your monthly income in Profile to unlock your budget.",
    "alert.overspent": "You spent {amount} more than your income this month.",
    "alert.needs_over": "Needs are over the {pct}% target by {amount}.",
    "alert.wants_over": "Wants are over the {pct}% target by {amount}.",
    "alert.savings_under": "You are below your {pct}% savings target this month.",

    "note.not_configured": "PayPal is not configured yet - every month below is sample data.",
    "note.read_failed": "Could not read PayPal - every month below is sample data.",
    "note.no_current": "No PayPal sandbox transactions found for this month yet (they can take a few hours to appear) - every month below is sample data.",
    "note.live": "{month} is live data from your PayPal sandbox account (test money).",
    "note.focus_past": "{today} has no PayPal sandbox activity yet, so FinAI is showing {focus}, your latest month with activity.",
    "note.sample_history": "{months} are sample history, because PayPal cannot create past-dated transactions.",
    "note.sample_prefix": "Sample data: ", "note.and": "and",
    "fx.note": "Amounts in other currencies are converted to {currency} with {source} rates from {date}.",
    "fx.missing": "{count} transaction(s) could not be converted because exchange rates are unavailable; they show their original currency.",

    "spend.title": "Transactions", "spend.refresh": "Re-analyze with AI", "spend.updated": "Analysis updated",
    "spend.month": "Month", "spend.category": "Category", "filter.all_months": "All months",
    "filter.all": "All", "filter.need": "Needs", "filter.want": "Wants", "filter.luxury": "Luxury", "filter.anomaly": "Unusual",
    "spend.search": "Search transactions...", "spend.help": "Tap a transaction to see the details and why Claude classified it.",
    "spend.nolib": "The table library could not load. Check your internet connection and reload.",
    "spend.empty": "Nothing here.", "spend.count": "{count} transactions · {amount} spent",
    "col.date": "Date", "col.description": "Description", "col.category": "Category", "col.amount": "Amount",
    "detail.title": "Transaction details", "detail.close": "Close", "detail.original_name": "Name in PayPal",
    "detail.charged": "Charged as", "detail.label": "AI label", "detail.reason": "Why Claude chose this category",
    "detail.unusual": "Unusual spending", "detail.yes": "Yes", "detail.no": "No", "detail.source": "Data",
    "detail.id": "Transaction ID", "detail.month": "Month",
    "tag.paypal": "PayPal sandbox", "tag.sample": "Sample", "tag.unusual": "Unusual", "tag.not_converted": "not converted",

    "goals.title": "Savings goals", "goals.help": "Every transfer is a real PayPal sandbox payout and always asks for your confirmation.",
    "goals.empty": "No goals yet. Add one below.", "goals.new": "New goal", "goals.name": "Name", "goals.target": "Target amount",
    "goals.add": "Add goal", "goals.added": "Goal added", "goals.transfer": "Transfer to goal", "goals.delete": "Delete",
    "goals.eta": "At {amount}/month you reach it in {months} month(s) · {eta}", "goals.reached": "Reached!",
    "goals.no_saving": "Set a monthly saving",
    "goals.delete_title": "Delete goal?", "goals.delete_body": "This removes the goal from FinAI. Money already transferred is not affected.",
    "goals.transfer_title": "Transfer to \"{goal}\"",
    "goals.transfer_body": "This sends a real <strong>PayPal sandbox payout</strong> to your savings account. Nothing moves until you confirm.",
    "goals.amount": "Amount ({currency})", "goals.confirm": "Confirm transfer",
    "goals.sent": "Sent {amount} via PayPal (batch {batch}, {status})",
    "pay.converted": "Your PayPal account works in {paypal}, so about {amount} will be sent (rate of {date}).",
    "history.title": "Transfer history", "history.empty": "No transfers yet.", "history.saved": "Saved to {name}", "history.paid": "Paid {name}",
    "history.batch": "PayPal batch {batch}", "history.sent": "sent {amount}",

    "bills.calendar": "Payment calendar", "bills.pending": "{count} pending · {amount}", "bills.fixed": "Fixed payments",
    "bills.legend_due": "Due", "bills.legend_paid": "Paid (on the day it was paid)", "bills.legend_auto": "Detected recurring",
    "bills.empty": "No fixed payments yet. Add rent, subscriptions or utilities below.", "bills.new": "New fixed payment",
    "bills.name": "Name", "bills.amount": "Amount", "bills.day": "Day of month",
    "bills.payee_note": "Payments go to your PayPal sandbox payee account, so no email is needed.",
    "bills.add": "Add payment", "bills.added": "Payment added", "bills.day_line": "Day {day} · {amount}",
    "bills.paid_on": "Paid {date}", "bills.paid_paypal_help": "A PayPal payment with this name and amount was found this month",
    "bills.pay": "Pay with PayPal", "bills.pay_title": "Pay \"{name}\"?",
    "bills.pay_body": "This sends <strong>{amount}</strong> as a real PayPal sandbox payout.",
    "bills.confirm": "Confirm payment", "bills.paid": "Paid {amount} via PayPal (batch {batch})",
    "bills.delete_title": "Delete payment?", "bills.delete_body": "This removes it from your calendar.",
    "bills.recurring": "Recurring payments found in your history",
    "bills.recurring_help": "FinAI found these charges every month. They are on the calendar too.",
    "bills.recurring_line": "Around day {day} · {amount} · seen in {months} months",
    "bills.make_fixed": "Add as fixed payment", "bills.recurring_empty": "No other recurring payments found.",

    "settings.title": "Settings", "settings.language": "Language", "settings.currency": "Home currency",
    "settings.help": "Changing the currency converts your income, goals and fixed payments at today's exchange rate. Purchases made in other currencies are converted automatically.",
    "settings.save": "Save settings", "settings.saved": "Settings saved",
    "settings.converted": "Converted at 1 {from} = {rate} {to}",

    "profile.title": "Financial profile",
    "profile.help": "This is typed in by you and stays in this app. FinAI only reads your PayPal activity, so your income comes from here.",
    "profile.income": "Monthly income ({currency})", "profile.targets": "Budget targets (% of income)",
    "profile.targets_help": "Luxury counts inside wants. The classic rule is 50 / 30 / 20. Changes show up everywhere: Home, alerts, health score and Claude's advice.",
    "profile.total_ok": "Total: 100% ✓", "profile.total_bad": "Total: {total}% (must be 100%)",
    "profile.save": "Save profile", "profile.saved": "Profile saved",
    "privacy.title": "Privacy & safety",
    "privacy.1": "PayPal is accessed only from the server with your app's sandbox credentials.",
    "privacy.2": "Money only moves after you confirm each transfer.",
    "privacy.3": "Analysis covers PayPal activity only, plus what you type in.",
    "privacy.4": "The AI receives transaction descriptions and amounts, never credentials.",

    "modal.confirm": "Confirm", "modal.cancel": "Cancel",
  },

  es: {
    "tab.home": "Inicio", "tab.spending": "Gastos", "tab.goals": "Metas", "tab.bills": "Pagos", "tab.profile": "Perfil",
    "badge.paypal": "PayPal {env}", "badge.paypal_off": "PayPal no conectado", "badge.ai": "IA de Claude", "badge.ai_off": "IA apagada",
    "loading.default": "Cargando tus finanzas...", "loading.settings": "Aplicando tu configuración. Claude está reescribiendo tu análisis...",
    "loading.refresh": "Claude está reanalizando tus gastos...",

    "home.hello": "Tu resumen financiero", "home.left": "Te queda en {month}", "home.left_over": "Te pasaste en {month}",
    "home.of_income": "Gastaste {spent} de {income} de ingreso", "home.score": "Salud", "home.spent": "Gastado",
    "home.free": "Libre después de pagos", "home.analyzing": "Analizando tus finanzas...",
    "home.budget": "Tu presupuesto {needs} / {wants} / {savings}", "home.of_income_short": "del ingreso",
    "home.target": "meta {amount} · {pct}%", "home.wants_target": "meta con lujos {amount} · {pct}%",
    "home.inside_wants": "cuenta dentro de deseos", "home.month_saved": "ahorro {amount}", "home.month_over": "excedido {amount}", "home.over": "Excedido", "home.ok": "En meta", "home.under": "Debajo de la meta",
    "home.months": "Mes a mes", "home.so_far": "(en lo que va)", "home.saved": "+{amount} ahorrado",
    "home.insights": "Consejos de la IA", "home.by_claude": "por Claude", "home.basic": "reglas básicas",
    "home.suggested": "Ahorro sugerido por la IA", "home.per_month": "{amount} / mes",
    "home.save_toward": "Ahorrarlo en \"{goal}\"", "home.create_goal": "Crear una meta",
    "home.sample_profile": "Perfil de ejemplo: el ingreso de {income} al mes, la meta y los pagos fijos son ejemplos para que el demo nunca empiece vacío.",
    "home.enter_income": "Escribe tu propio ingreso",
    "cat.need": "necesidad", "cat.want": "deseo", "cat.luxury": "lujo", "cat.saving": "ahorro", "cat.income": "ingreso",
    "legend.needs": "Necesidades", "legend.wants": "Deseos", "legend.luxury": "Lujos", "legend.savings": "Ahorro",

    "alert.no_income": "Escribe tu ingreso mensual en Perfil para ver tu presupuesto.",
    "alert.overspent": "Este mes gastaste {amount} más que tu ingreso.",
    "alert.needs_over": "Las necesidades pasan la meta del {pct}% por {amount}.",
    "alert.wants_over": "Los deseos pasan la meta del {pct}% por {amount}.",
    "alert.savings_under": "Este mes estás debajo de tu meta de ahorro del {pct}%.",

    "note.not_configured": "PayPal aún no está configurado: todos los meses son datos de ejemplo.",
    "note.read_failed": "No se pudo leer PayPal: todos los meses son datos de ejemplo.",
    "note.no_current": "Todavía no hay transacciones de PayPal sandbox este mes (pueden tardar unas horas en aparecer): todos los meses son datos de ejemplo.",
    "note.live": "Los datos de {month} vienen en vivo de tu cuenta PayPal sandbox (dinero de prueba).",
    "note.focus_past": "En {today} todavía no hay actividad en PayPal sandbox, así que FinAI muestra {focus}, tu último mes con actividad.",
    "note.sample_history": "Los de {months} son historial de ejemplo, porque PayPal no permite crear transacciones con fechas pasadas.",
    "note.sample_prefix": "Datos de ejemplo: ", "note.and": "y",
    "fx.note": "Los montos en otras monedas se convierten a {currency} con tipos de cambio de {source} del {date}.",
    "fx.missing": "{count} transacción(es) no se pudieron convertir porque el tipo de cambio no está disponible; se muestran en su moneda original.",

    "spend.title": "Transacciones", "spend.refresh": "Reanalizar con IA", "spend.updated": "Análisis actualizado",
    "spend.month": "Mes", "spend.category": "Categoría", "filter.all_months": "Todos los meses",
    "filter.all": "Todas", "filter.need": "Necesidades", "filter.want": "Deseos", "filter.luxury": "Lujos", "filter.anomaly": "Inusuales",
    "spend.search": "Buscar transacciones...", "spend.help": "Toca una transacción para ver el detalle y por qué Claude la clasificó así.",
    "spend.nolib": "No se pudo cargar la tabla. Revisa tu conexión a internet y recarga.",
    "spend.empty": "No hay nada aquí.", "spend.count": "{count} transacciones · {amount} gastado",
    "col.date": "Fecha", "col.description": "Descripción", "col.category": "Categoría", "col.amount": "Monto",
    "detail.title": "Detalle de la transacción", "detail.close": "Cerrar", "detail.original_name": "Nombre en PayPal",
    "detail.charged": "Cobrado en", "detail.label": "Etiqueta de la IA", "detail.reason": "Por qué Claude eligió esta categoría",
    "detail.unusual": "Gasto inusual", "detail.yes": "Sí", "detail.no": "No", "detail.source": "Datos",
    "detail.id": "ID de transacción", "detail.month": "Mes",
    "tag.paypal": "PayPal sandbox", "tag.sample": "Ejemplo", "tag.unusual": "Inusual", "tag.not_converted": "sin convertir",

    "goals.title": "Metas de ahorro", "goals.help": "Cada transferencia es un pago real de PayPal sandbox y siempre pide tu confirmación.",
    "goals.empty": "Aún no tienes metas. Agrega una abajo.", "goals.new": "Nueva meta", "goals.name": "Nombre", "goals.target": "Monto objetivo",
    "goals.add": "Agregar meta", "goals.added": "Meta agregada", "goals.transfer": "Transferir a la meta", "goals.delete": "Borrar",
    "goals.eta": "Con {amount}/mes la alcanzas en {months} mes(es) · {eta}", "goals.reached": "¡Lograda!",
    "goals.no_saving": "Define un ahorro mensual",
    "goals.delete_title": "¿Borrar meta?", "goals.delete_body": "Esto quita la meta de FinAI. El dinero ya transferido no cambia.",
    "goals.transfer_title": "Transferir a \"{goal}\"",
    "goals.transfer_body": "Esto envía un <strong>pago real de PayPal sandbox</strong> a tu cuenta de ahorro. No se mueve nada hasta que confirmes.",
    "goals.amount": "Monto ({currency})", "goals.confirm": "Confirmar transferencia",
    "goals.sent": "Enviado {amount} con PayPal (lote {batch}, {status})",
    "pay.converted": "Tu cuenta PayPal trabaja en {paypal}, así que se enviarán unos {amount} (tipo de cambio del {date}).",
    "history.title": "Historial de transferencias", "history.empty": "Aún no hay transferencias.", "history.saved": "Ahorrado en {name}", "history.paid": "Pagado: {name}",
    "history.batch": "Lote PayPal {batch}", "history.sent": "enviado {amount}",

    "bills.calendar": "Calendario de pagos", "bills.pending": "{count} pendientes · {amount}", "bills.fixed": "Pagos fijos",
    "bills.legend_due": "Por pagar", "bills.legend_paid": "Pagado (el día en que se pagó)", "bills.legend_auto": "Recurrente detectado",
    "bills.empty": "Aún no hay pagos fijos. Agrega renta, suscripciones o servicios abajo.", "bills.new": "Nuevo pago fijo",
    "bills.name": "Nombre", "bills.amount": "Monto", "bills.day": "Día del mes",
    "bills.payee_note": "Los pagos van a tu cuenta PayPal sandbox de destino, así que no hace falta un email.",
    "bills.add": "Agregar pago", "bills.added": "Pago agregado", "bills.day_line": "Día {day} · {amount}",
    "bills.paid_on": "Pagado el {date}", "bills.paid_paypal_help": "Este mes hay un pago de PayPal con este nombre y monto",
    "bills.pay": "Pagar con PayPal", "bills.pay_title": "¿Pagar \"{name}\"?",
    "bills.pay_body": "Esto envía <strong>{amount}</strong> como pago real de PayPal sandbox.",
    "bills.confirm": "Confirmar pago", "bills.paid": "Pagado {amount} con PayPal (lote {batch})",
    "bills.delete_title": "¿Borrar pago?", "bills.delete_body": "Esto lo quita de tu calendario.",
    "bills.recurring": "Pagos recurrentes encontrados en tu historial",
    "bills.recurring_help": "FinAI encontró estos cargos cada mes. También aparecen en el calendario.",
    "bills.recurring_line": "Alrededor del día {day} · {amount} · visto en {months} meses",
    "bills.make_fixed": "Agregar como pago fijo", "bills.recurring_empty": "No se encontraron otros pagos recurrentes.",

    "settings.title": "Configuración", "settings.language": "Idioma", "settings.currency": "Moneda principal",
    "settings.help": "Al cambiar la moneda, tu ingreso, metas y pagos fijos se convierten con el tipo de cambio de hoy. Las compras en otras monedas se convierten solas.",
    "settings.save": "Guardar configuración", "settings.saved": "Configuración guardada",
    "settings.converted": "Convertido a 1 {from} = {rate} {to}",

    "profile.title": "Perfil financiero",
    "profile.help": "Esto lo escribes tú y se queda en esta app. FinAI solo lee tu actividad de PayPal, así que tu ingreso sale de aquí.",
    "profile.income": "Ingreso mensual ({currency})", "profile.targets": "Metas del presupuesto (% del ingreso)",
    "profile.targets_help": "Los lujos cuentan dentro de los deseos. La regla clásica es 50 / 30 / 20. Los cambios se ven en toda la app: Inicio, alertas, salud financiera y consejos de Claude.",
    "profile.total_ok": "Total: 100% ✓", "profile.total_bad": "Total: {total}% (debe sumar 100%)",
    "profile.save": "Guardar perfil", "profile.saved": "Perfil guardado",
    "privacy.title": "Privacidad y seguridad",
    "privacy.1": "PayPal solo se usa desde el servidor, con las credenciales sandbox de la app.",
    "privacy.2": "El dinero solo se mueve después de que confirmas cada transferencia.",
    "privacy.3": "El análisis cubre solo tu actividad de PayPal y lo que tú escribes.",
    "privacy.4": "La IA recibe descripciones y montos de las transacciones, nunca credenciales.",

    "modal.confirm": "Confirmar", "modal.cancel": "Cancelar",
  },
};

// Names of the built-in sample goal and bills, so they follow the language too.
// Names the user types are shown exactly as typed.
const SAMPLE_NAMES = {
  es: { "Emergency fund": "Fondo de emergencia", "Rent": "Renta", "Electricity": "Luz",
        "Internet": "Internet", "Phone plan": "Plan de celular" },
};

const LOCALES = { en: "en-US", es: "es-MX" };

function t(key, vars = {}) {
  const table = STRINGS[state.language] || STRINGS.en;
  const text = table[key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? `{${name}}`));
}

// A sample goal/bill name in the user's language (user-typed names stay as they are).
function itemName(item) {
  if (!item.sample) return item.name;
  return (SAMPLE_NAMES[state.language] || {})[item.name] || item.name;
}

// Fill every element marked with data-i18n (text) or data-i18n-placeholder (input hint).
function applyStaticTranslations() {
  document.documentElement.lang = state.language;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}
