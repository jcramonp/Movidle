# m o v i d l e
Proyecto Django para la aplicación **MovieGame**, un juego interactivo basado en películas.  
Esta API se utiliza para manejar datos relacionados con el juego y llenar la base de datos.

---
## ⚙️ Instalación y configuración

1. **Clonar el repositorio**
   
   git clone https://github.com/tu_usuario/MovidleProject.git
   cd MovidleProject

2. **Crear y activar un entorno virtual**

python -m venv venv
* En Windows
venv\Scripts\activate
* En Linux/Mac
source venv/bin/activate


3. **Instalar dependencias**

pip install -r requirements.txt


4. **Aplicar migraciones**

python manage.py migrate


5. **Crear un superusuario (opcional, para acceder al panel de administración)**

python manage.py createsuperuser

6. **Ejecutar el servidor**

Inicia el servidor de desarrollo con:

python manage.py runserver

Por defecto, estará disponible en:

👉 http://127.0.0.1:8000/



