#!/bin/bash
set -e
echo "🧹 حذف الملفات غير المستخدمة..."
rm -rf client shared server/routes.ts server/storage.ts server/vite.ts server/static.ts \
       drizzle.config.ts components.json tailwind.config.ts postcss.config.js \
       vite.config.ts tsconfig.json script dist __pycache__

echo "📝 كتابة package.json مبسّط..."
cat > package.json << 'EOF'
{
  "name": "weekly-plan-proxy",
  "version": "1.0.0",
  "type": "module",
  "license": "MIT",
  "description": "Thin Node.js proxy that starts and forwards requests to the real app (Flask/main.py). No other Node dependencies are needed.",
  "scripts": {
    "dev": "NODE_ENV=development tsx server/index.ts",
    "build": "echo 'No Node build needed - the app is Flask (main.py), served directly by gunicorn in production.'"
  },
  "devDependencies": {
    "tsx": "^4.20.5"
  }
}
EOF

echo "📦 إعادة تثبيت الحزم (سيصبح العدد 3 فقط بدل 470)..."
rm -rf node_modules package-lock.json
npm install

echo "✅ تم! الآن راجع بأمر: git status"