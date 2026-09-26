/* ==========================================================================
   Site-wide Arabic / English switch.

   Arabic stays the single source of truth in the templates and on the server.
   In English mode this script translates, in place and without reloading:
   text, placeholders, titles, aria-labels, the page title, messages added later
   by scripts (toasts, flash messages, server replies) and alert/confirm dialogs.

   Teacher-written content (topics, homework, names, file names) is never
   translated: it is either inside a <textarea> or marked translate="no".
   ========================================================================== */
(function () {
  'use strict';

  var STORE_KEY = 'site-lang';
  var NAMES = window.I18N_NAMES || {};          // e.g. {"مدارس ثقافة الجيل": "Al-Jeel Schools"} from Settings
  var AR = /[؀-ۿ]/;

  /* ---------------------------------------------------------------------
     Dictionary (exact phrases, whitespace-normalised)
     --------------------------------------------------------------------- */
  var DICT = {
    /* ---- common ---- */
    'العربية': 'العربية',
    'اختيار اللغة': 'Choose language',
    'نظام الخطة الدراسية': 'Weekly Plan System',
    'نظام الخطة الدراسية الأسبوعية': 'Weekly Plan System',
    'الخطة الأسبوعية': 'Weekly Plan',
    'الخطة': 'Weekly',
    'الأسبوعية': 'Plan',
    'أنشئ هذا الموقع بواسطة أحمد الفيفي': 'Built by Ahmed Al-Faifi',
    'تسجيل الدخول': 'Sign in',
    'تسجيل الخروج': 'Sign out',
    'الصفحة الرئيسية': 'Home',
    'الأحد': 'Sunday', 'الاثنين': 'Monday', 'الإثنين': 'Monday', 'الثلاثاء': 'Tuesday',
    'الأربعاء': 'Wednesday', 'الخميس': 'Thursday', 'الجمعة': 'Friday', 'السبت': 'Saturday',
    'اليوم': 'Today',
    'الأسبوع': 'Week',
    'الصف': 'Grade',
    'الفصل': 'Class',
    'المادة': 'Subject',
    'الموضوع': 'Topic',
    'الواجب': 'Homework',
    'الواجب:': 'Homework:',
    'الموضوع والواجب': 'Topic & homework',
    'الحالي': 'current',
    '(الحالي)': '(current)',
    'الأحدث': 'latest',
    '(غير معتمد)': '(not approved)',
    'حفظ': 'Save',
    'إضافة': 'Add',
    'تعديل': 'Edit',
    'حذف': 'Delete',
    'نقل': 'Move',
    'نسخ': 'Copy',
    'إلغاء': 'Clear',
    'إغلاق': 'Close',
    'طباعة': 'Print',
    'مسح': 'Clear',
    'عام': 'General',
    'الكل': 'All',
    'التالي': 'Next',
    'السابق': 'Previous',
    'الصفحة': 'Page',
    'خطأ': 'Error',
    'خطأ:': 'Error:',
    'مكتمل': 'Complete',
    'مكتمل ✓': 'Complete ✓',
    'مكتملة ✓': 'Complete ✓',
    'مغلق': 'Locked',
    'معتمد': 'Approved',
    'مسودة': 'Draft',
    'مفعل': 'Active',
    'معطل': 'Inactive',
    'تعطيل': 'Disable',
    'تفعيل': 'Enable',
    'المدير': 'Admin',
    'مدير': 'Admin',
    'معلم': 'Teacher',
    'مشرف': 'Supervisor',
    '· مشرف': '· Supervisor',
    'مدارس الثقافة الرقمية': 'Digital Culture Schools',
    'جاري الحفظ...': 'Saving...',
    'جاري الرفع...': 'Uploading...',
    'جاري التجهيز...': 'Preparing...',
    'جاري الدخول...': 'Signing in...',
    'تم الحفظ': 'Saved',
    'تم الحفظ بنجاح ✓': 'Saved successfully ✓',
    'لا توجد تغييرات': 'No changes',
    'لا توجد تغييرات للحفظ': 'Nothing to save',
    'فشل الاتصال بالخادم': 'Could not reach the server',
    'فشل الاتصال بالخادم — يرجى المحاولة مرة أخرى': 'Could not reach the server — please try again',
    'خطأ في الاتصال بالخادم': 'Server connection error',
    '✗ فشل الاتصال': '✗ Connection failed',
    '✗ فشل الحفظ': '✗ Save failed',
    '✗ فشل الحفظ:': '✗ Save failed:',

    /* ---- home / landing ---- */
    'دروس الأسبوع وواجباته وملفاته، في جدول واحد.': "The week's lessons, homework and files in one timetable.",
    'دروس الأسبوع وواجباته وملفاته، في جدول واحد يصل للطالب وولي الأمر.': "The week's lessons, homework and files in one timetable for students and parents.",
    'جدول الطالب': 'Student timetable',
    'لأولياء الأمور والطلاب — بدون تسجيل دخول': 'For parents and students — no sign-in needed',
    'للمعلمين والمشرفين والإدارة': 'For teachers, supervisors and admin',
    'الأسبوع الحالي': 'Current week',
    'اختر الفصل': 'Choose a class',
    'لعرض الجدول الأسبوعي والدروس والواجبات والملفات.': 'To see the weekly timetable, lessons, homework and files.',
    'لا توجد صفوف مسجلة حالياً': 'No grades have been added yet',
    'لا توجد فصول': 'No classes',

    /* ---- login ---- */
    'للمعلمين والمشرفين وإدارة المدرسة': 'For teachers, supervisors and school admin',
    'اسم المستخدم': 'Username',
    'كلمة المرور': 'Password',
    'للمدير: اتركه فارغاً أو اكتب admin': 'Admin: leave empty or type admin',
    'إظهار كلمة المرور': 'Show password',
    'إخفاء كلمة المرور': 'Hide password',
    'عرض جدول الطالب': 'Student timetable',
    'اسم المستخدم أو كلمة المرور غير صحيحة': 'Incorrect username or password',
    'تسجيل الدخول - نظام الخطة الدراسية': 'Sign in - Weekly Plan System',

    /* ---- student page ---- */
    'أعزاءنا أولياء الأمور والطلاب الكرام.. نرحب بكم في منصة (الجدول الذكي)؛ وجهتكم المعتمدة للاطلاع على الخطة الأسبوعية، والتي نوافيكم بها بدقة وموعد ثابت كل يوم خميس بنهاية دوامنا الدراسي، لنعينكم على التخطيط المبكر لأسبوعكم القادم.':
      'Dear parents and students, welcome to the Smart Schedule platform — your trusted place to view the weekly plan, published every Thursday at the end of the school day to help you plan the coming week.',
    'اضغط لقراءة الرسالة كاملة': 'Tap to read the full message',
    'لم يتم اعتماد الجدول بعد': 'The schedule has not been published yet',
    'اختر الأسبوع': 'Choose a week',
    'اختيار الأسبوع': 'Choose a week',
    'اختبارات الفترة الأولى': 'First assessment',
    'اختبارات الفترة الثانية': 'Second assessment',
    'الاختبار النهائي': 'Final exam',
    'يوم متبقٍ': 'days left',
    'اليوم / الحصة': 'Day / Period',
    'اضغط على أي مادة لعرض التفاصيل والملفات': 'Tap any subject to see details and files',
    'لا يوجد ملف مرفق لهذه الحصة': 'No file attached to this lesson',
    'لا توجد ملفات أو روابط لهذه الحصة': 'No files or links for this lesson',
    'يوجد رابط': 'Has a link',
    'إضافة رابط': 'Add link',
    'رابط يوتيوب أو أي موقع': 'YouTube or any website link',
    'عنوان (اختياري)': 'Title (optional)',
    'حفظ الرابط': 'Save link',
    'حذف الرابط': 'Remove link',
    'حذف هذا الرابط؟': 'Remove this link?',
    'تمت إضافة الرابط': 'Link added',
    'تم حذف الرابط': 'Link removed',
    'تعذر حفظ الرابط': 'Could not save the link',
    'تعذر حذف الرابط': 'Could not remove the link',
    'الرابط غير موجود': 'Link not found',
    'غير مصرح بحذف هذا الرابط': 'You are not allowed to remove this link',
    'الرابط غير صحيح — تأكد أنه يبدأ بـ https://': 'That link is not valid — make sure it starts with https://',
    'فيديو يوتيوب': 'YouTube video',
    'يوجد ملف مرفق': 'File attached',
    'لا توجد حصة': 'Free period',
    'عرض الأسبوع كاملاً': 'Full week view',
    'عرض يوم واحد': 'Day view',
    'تحميل PDF (A4)': 'Download PDF (A4)',
    'حفظ كصورة': 'Save as image',
    'أيام الأسبوع': 'Days of the week',
    'جدول اليوم': "Day's timetable",
    'الجدول الأسبوعي': 'Weekly timetable',
    'تم تحديث الخطة ✓': 'The plan was updated ✓',
    'معاينة للإدارة:': 'Staff preview:',
    'عطلة نهاية الأسبوع': 'weekend',

    /* ---- teacher / supervisor schedule ---- */
    'لوحة تحكم المعلم': 'Teacher dashboard',
    'لوحة المعلم': 'Teacher dashboard',
    'الأسبوع الدراسي': 'School week',
    'اختر الصف...': 'Choose a grade...',
    'اختر الفصل...': 'Choose a class...',
    'اختر الصف والفصل': 'Choose a grade and class',
    'يظهر جدول الأسبوع هنا لتعبئة الدروس والواجبات ورفع الملفات.': "The week's timetable appears here so you can fill in lessons, homework and files.",
    'اكتب موضوع الدرس والواجب، وأرفق ملفاً للحصة إن وُجد. الملفات تُحفظ فور رفعها.': 'Write the lesson topic and homework, and attach a file if you have one. Files are saved as soon as they upload.',
    'يمكنك مراجعة جميع الحصص وتعديلها. الحصة الناقصة تحتاج موضوع الدرس والواجب معاً.': 'You can review and edit every lesson. A lesson is complete when it has both a topic and homework.',
    '→ الفصل السابق': '← Previous class',
    'الفصل التالي ←': 'Next class →',
    'التنقل بين الفصول': 'Move between classes',
    'الحصة الناقصة التالية': 'Next missing lesson',
    'إبراز الناقص فقط': 'Highlight missing only',
    'عرض حصصي فقط': 'Show my lessons only',
    'مكتمل ✓ جميع الحصص محضّرة': 'Complete ✓ every lesson is ready',
    'ناقص: الموضوع': 'Missing: topic',
    'ناقص: الواجب': 'Missing: homework',
    'ناقص: الموضوع والواجب': 'Missing: topic & homework',
    'موضوع الدرس...': 'Lesson topic...',
    'الواجب المنزلي...': 'Homework...',
    'لم يُدخل بعد...': 'Not entered yet...',
    'للعرض فقط': 'View only',
    'لا توجد مادة': 'No subject',
    'هذا اليوم مغلق': 'This day is locked',
    'لا توجد حصص مخصصة لك في هذا اليوم': 'You have no lessons on this day',
    'حفظ الدرس والواجب': 'Save lessons & homework',
    'إرفاق ملف': 'Attach file',
    'حذف الملف': 'Delete file',
    'تم حذف الملف': 'File deleted',
    'تعذر حذف الملف': 'Could not delete the file',
    'فشل رفع الملف': 'Upload failed',
    'تم رفع الملف — يظهر للطالب عند اعتماد الأسبوع': 'File uploaded — students see it once the week is published',
    'متابعة الأسبوع': 'Weekly follow-up',
    'لوحة المدير': 'Admin dashboard',
    'انتهت جلسة العمل — يرجى تسجيل الدخول مجدداً': 'Your session has ended — please sign in again',
    'غير مصرح — هذه المادة ليست مخصصة لك': 'Not allowed — this lesson is not assigned to you',
    'غير مصرح بحذف هذا الملف': 'You are not allowed to delete this file',
    'هذا اليوم مغلق من الإدارة': 'This day has been locked by the admin',
    'رقم الحصة خارج النطاق المسموح': 'Period number is out of range',
    'بيانات الحصة ناقصة': 'Lesson details are missing',
    'بيانات ناقصة': 'Missing data',
    'الفصل غير موجود': 'Class not found',
    'الملف غير موجود': 'File not found',
    'الملف فارغ': 'The file is empty',
    'اختر ملفاً أولاً': 'Choose a file first',
    'فشل حفظ الملف — حاول مرة أخرى': 'Could not save the file — try again',
    'تعذر الوصول لمساحة التخزين — حاول مرة أخرى': 'Storage is unavailable — try again',
    'فشل الحفظ في قاعدة البيانات — يرجى المحاولة مجدداً': 'Could not save to the database — please try again',
    'نوع الملف غير مدعوم. المسموح: PDF و Word و PowerPoint و Excel والصور والصوت والفيديو و TXT و ZIP':
      'File type not supported. Allowed: PDF, Word, PowerPoint, Excel, images, audio, video, TXT and ZIP',
    'الملف أكبر من الحد المسموح': 'The file is larger than allowed',

    /* ---- weekly follow-up (supervisor) ---- */
    'متابعة الخطة الأسبوعية': 'Weekly plan follow-up',
    'الحصة مكتملة عندما يُكتب موضوع الدرس والواجب معاً. الفصل لا يُعد مكتملاً إلا عند اكتمال جميع حصصه هذا الأسبوع': 'A lesson is complete when it has both a topic and homework. A class is complete only when every lesson this week is complete',
    '(الأيام المغلقة لا تُحتسب)': '(locked days are not counted)',
    'الحصة مكتملة عندما يُكتب موضوع الدرس والواجب معاً. الفصل لا يُعد مكتملاً إلا عند اكتمال جميع حصصه هذا الأسبوع.': 'A lesson is complete when it has both a topic and homework. A class is complete only when every lesson this week is complete.',
    'اسم المدرسة بالإنجليزية:': 'School name in English:',
    'يظهر عند اختيار English. اتركه فارغاً لإظهار الاسم العربي.': 'Shown when English is selected. Leave empty to keep the Arabic name.',
    'هذا هو الأسبوع الحالي، ويظهر لأولياء الأمور تلقائياً ويتحدّث عندهم مباشرة (من الإعدادات).': 'This is the current week. Parents see it automatically and it updates live (from Settings).',
    'فصول مكتملة بالكامل': 'Fully complete classes',
    'حصة ناقصة': 'missing lessons',
    'وين النقص؟': 'Where are the gaps?',
    'الرقم الأحمر = عدد الحصص الناقصة في ذلك اليوم. اضغط عليه أو على اسم الفصل لفتح الجدول الكامل وتعديله.': 'Red number = missing lessons that day. Tap it, or the class name, to open and edit the full timetable.',
    'طباعة التقرير': 'Print report',
    'الإنجاز': 'Progress',
    'اعتماد لأولياء الأمور': 'Published to parents',
    'ظاهر تلقائياً': 'Shown automatically',
    'فتح الجدول': 'Open timetable',
    'مجموع النقص': 'Total missing',
    'الفصول المحددة تظهر لأولياء الأمور. يمكن اعتماد فصل ناقص، لكن يُفضّل إكماله أولاً. إلغاء التحديد يسحب الاعتماد فوراً.': 'Selected classes are visible to parents. You can publish an incomplete class, but it is better to complete it first. Unticking removes it immediately.',
    'تحديد المكتملة فقط': 'Select complete only',
    'حفظ الاعتماد': 'Save publishing',
    'تفاصيل الحصص الناقصة': 'Missing lessons in detail',
    'كل حصة ناقصة مع ما ينقصها. اضغط على الحصة لفتحها وتعديلها مباشرة.': 'Every missing lesson and what it lacks. Tap a lesson to open and edit it.',
    'جميع الفصول مكتملة لهذا الأسبوع ✓': 'Every class is complete this week ✓',

    /* ---- activity log ---- */
    'سجل النشاطات (Activity Log)': 'Activity log',
    'تصفية السجلات': 'Filter records',
    'اسم المعلم': 'Teacher name',
    'بحث بالاسم...': 'Search by name...',
    'نوع العملية': 'Action type',
    'التاريخ': 'Date',
    'تصفية': 'Filter',
    'إجمالي السجلات': 'Total records',
    'التاريخ والوقت': 'Date & time',
    'الدور': 'Role',
    'الهدف': 'Target',
    'التفاصيل': 'Details',
    'المستخدم': 'User',
    'لا توجد سجلات مطابقة للتصفية المحددة': 'No records match this filter',
    'لوحة التحكم': 'Dashboard',
    'تقرير التدقيق': 'Audit report',
    'حفظ درس/واجب': 'Save lesson/homework',
    'نقل (سحب وإفلات)': 'Move (drag & drop)',
    'تسجيل دخول': 'Sign in',
    'تسجيل خروج': 'Sign out',
    'مرفق': 'Attachment',
    'استيراد': 'Import',
    'اعتماد': 'Publish',
    'توزيع': 'Assignment',
    'تم تسجيل الدخول للوحة التحكم': 'Signed in to the dashboard',
    'تم تسجيل الخروج': 'Signed out',

    /* ---- admin dashboard ---- */
    'لوحة تحكم المدير': 'Admin dashboard',
    'الرئيسية': 'Overview',
    'الإحصائيات': 'Statistics',
    'استيراد Excel': 'Import Excel',
    'إدارة الجدول': 'Schedule',
    'الجدول الأساسي': 'Master schedule',
    'التجاوز الأسبوعي': 'Weekly overrides',
    'المستخدمون': 'Users',
    'الصفوف والفصول': 'Grades & classes',
    'المعلمون': 'Teachers',
    'المشرفون': 'Supervisors',
    'توزيع المواد': 'Assignments',
    'أخرى': 'Other',
    'روابط الطلاب': 'Student links',
    'الإعدادات': 'Settings',
    'إحصائيات الإنجاز': 'Completion statistics',
    'لا توجد بيانات بعد — قم برفع ملف Excel أولاً': 'No data yet — upload an Excel file first',
    'نسبة إنجاز الحصص': 'Lessons completed',
    'حصص مكتملة (موضوع + واجب)': 'Complete lessons (topic + homework)',
    'مراجعة الجدول واعتماده لأولياء الأمور': 'Review timetable & publish to parents',
    'مراجعة الجدول واعتماده': 'Review & publish timetable',
    'لا توجد فصول مكتملة بعد': 'No complete classes yet',
    'جميع الفصول مكتملة 🎉': 'All classes are complete 🎉',
    'سجل العمليات': 'Activity log',
    'السجل الكامل': 'Full log',
    'الوقت': 'Time',
    'النوع': 'Type',
    'استيراد الجدول المدرسي من Excel': 'Import the school timetable from Excel',
    'اختر ملف Excel (.xlsx) أو CSV': 'Choose an Excel (.xlsx) or CSV file',
    'رفع واستيراد': 'Upload & import',
    'يقبل ملف برنامج الجداول كما هو: العمود الأول اسم الفصل (مثال:': 'Accepts the timetable program file as-is: the first column is the class name (e.g.',
    '← الصف': '→ grade',
    'والفصل': 'and class',
    ')، وصف العناوين يحتوي أسماء الأيام وأرقام الحصص. يُقرأ اسم المادة من السطر الأول في الخانة، ويُضبط عدد الحصص اليومية تلقائياً. بيانات المعلمين (الدروس والواجبات) لا تُمسح عند إعادة الاستيراد.':
      '), and the header row holds day names and period numbers. The subject is read from the first line of each cell and the periods per day are set automatically. Teachers’ lessons and homework are kept when you re-import.',
    'إدارة التجاوز الأسبوعي': 'Weekly overrides',
    'اختر الفصل:': 'Choose class:',
    'اختر الأسبوع:': 'Choose week:',
    'تغيير المادة...': 'Change subject...',
    'حفظ التعديلات الأسبوعية بالكامل': 'Save all weekly changes',
    'يرجى اختيار الفصل لعرض وتعديل التجاوزات الأسبوعية': 'Choose a class to view and edit weekly overrides',
    'الإعدادات العامة وشعار المدرسة': 'General settings & school logo',
    'تغيير شعار المدرسة:': 'Change school logo:',
    'رفع الشعار': 'Upload logo',
    'اسم المدرسة:': 'School name:',
    'الأسبوع الدراسي الحالي:': 'Current school week:',
    'إظهار الأسبوع الحالي لأولياء الأمور تلقائياً': 'Show the current week to parents automatically',
    'صفحات أولياء الأمور تفتح على هذا الأسبوع وتتحدّث وحدها عند تغييره أو تعديل الخطة.': 'Parent pages open on this week and refresh by themselves when it or the plan changes.',
    'عدد الحصص اليومية:': 'Periods per day:',
    'تاريخ اختبارات الفترة الأولى:': 'First assessment date:',
    'تاريخ اختبارات الفترة الثانية:': 'Second assessment date:',
    'تاريخ الاختبار النهائي:': 'Final exam date:',
    'حفظ الإعدادات': 'Save settings',
    'قفل الأيام حسب الأسبوع': 'Lock days by week',
    'اختر الأسبوع لإدارته:': 'Choose a week to manage:',
    'مسح مواعيد الاختبارات:': 'Clear assessment dates:',
    'مسح تاريخ الفترة 1': 'Clear assessment 1 date',
    'مسح تاريخ الفترة 2': 'Clear assessment 2 date',
    'مسح التاريخ النهائي': 'Clear final exam date',
    'إدارة الصفوف': 'Manage grades',
    'إدارة الفصول': 'Manage classes',
    'حذف جميع الصفوف': 'Delete all grades',
    'يحذف جميع الصفوف والفصول والجداول والخطط الأسبوعية وتوزيعات الحصص المرتبطة بها. لا يمكن التراجع عن هذه العملية.': 'Deletes all grades, classes, timetables, weekly plans and related assignments. This cannot be undone.',
    'اسم الصف': 'Grade name',
    'إدارة الجدول الأساسي': 'Manage master schedule',
    'اختر الفصل لتعديل جدوله الأساسي:': 'Choose a class to edit its master schedule:',
    'حفظ الجدول الأساسي بالكامل': 'Save the whole master schedule',
    'إدارة حسابات المعلمين': 'Teacher accounts',
    'إضافة معلم جديد': 'Add a new teacher',
    'رفع حسابات المعلمين من Excel': 'Import teacher accounts from Excel',
    'إضافة المعلم': 'Add teacher',
    'رفع واستيراد المعلمين': 'Upload & import teachers',
    '* أعمدة الملف: الاسم، اسم المستخدم، كلمة المرور': '* File columns: name, username, password',
    'الاسم': 'Name',
    'الحالة': 'Status',
    'إجراءات': 'Actions',
    'لا يوجد معلمون مسجلون بعد': 'No teachers yet',
    'حذف جميع حسابات المعلمين': 'Delete all teacher accounts',
    'يحذف الحسابات وتوزيعات الحصص، مع الاحتفاظ بموضوعات الدروس والواجبات المحفوظة في الخطط الأسبوعية.': 'Deletes the accounts and their assignments, but keeps the lessons and homework saved in weekly plans.',
    'حذف جميع الحسابات': 'Delete all accounts',
    'حذف جميع المعلمين': 'Delete all teachers',
    'حسابات المشرفين (مراجعة واعتماد فقط)': 'Supervisor accounts',
    'حساب المشرف يدخل مباشرة على شاشة "مراجعة الجدول واعتماده" فقط، ولا يملك صلاحية الوصول للوحة التحكم الكاملة أو تعديل الجداول.': 'Supervisors land on the weekly follow-up page. They can review and edit every lesson and publish weeks, but cannot open the admin dashboard.',
    'إضافة مشرف جديد': 'Add a new supervisor',
    'اسم المشرف': 'Supervisor name',
    'إضافة المشرف': 'Add supervisor',
    'لا يوجد مشرفون مسجلون بعد': 'No supervisors yet',
    'توزيع المواد على المعلمين': 'Assign lessons to teachers',
    'خصص الحصص لكل معلم. الحصص المحجوزة لمعلم آخر تظهر باللون الأصفر ولا يمكن تعيينها.': 'Assign periods to each teacher. Periods taken by another teacher are yellow and cannot be selected.',
    'المعلم المحدد:': 'Selected teacher:',
    'تحديد المتاح': 'Select available',
    'إلغاء الكل': 'Clear all',
    'حفظ التوزيع': 'Save assignments',
    'مخصص لك': 'Assigned to this teacher',
    'متاح': 'Available',
    'محجوز لمعلم آخر': 'Taken by another teacher',
    'اختر معلماً من القائمة أعلاه لعرض وتعديل حصصه': "Choose a teacher above to see and edit their periods",
    'أضف معلمين أولاً قبل توزيع المواد': 'Add teachers before assigning lessons',
    'اختر معلماً': 'Choose a teacher',
    'اختر معلماً أولاً': 'Choose a teacher first',
    'تحديد الفصل': 'Select class',
    'إلغاء الفصل': 'Clear class',
    'تحديد المادة': 'Select subject',
    'روابط الطلاب للفصول': 'Student links by class',
    'رابط الطالب': 'Student link',
    'تم نسخ الرابط بنجاح!': 'Link copied!',
    '-- اختر الفصل --': '-- Choose a class --',
    '-- اختر معلماً --': '-- Choose a teacher --',
    'المادة...': 'Subject...',
    'للمادة...': 'Subject...',
    'مثال: الصف الأول': 'e.g. Grade 1',
    'مثال: أ': 'e.g. A',
    'مثال: أحمد محمد': 'e.g. Ahmed Mohammed',
    'مثال: سارة العتيبي': 'e.g. Sara Alotaibi',
    'مثال: ahmed': 'e.g. ahmed',
    'مثال: sara': 'e.g. sara',
    'كلمة مرور المعلم': 'Teacher password',
    'كلمة مرور المشرف': 'Supervisor password',
    'كلمة المرور الجديدة:': 'New password:',
    'لا توجد مواد في الجدول الأساسي بعد. يرجى رفع الجدول أولاً.': 'No subjects in the master schedule yet. Import the timetable first.',
    'هل أنت متأكد من حذف الفصل؟': 'Delete this class?',
    'هل أنت متأكد؟ سيتم حذف جميع الفصول والمواد المرتبطة.': 'Are you sure? All its classes and subjects will be deleted.',
    'هل تريد حذف هذا المشرف؟': 'Delete this supervisor?',
    'هل تريد حذف هذا المعلم؟': 'Delete this teacher?',
    'عبارة التأكيد غير صحيحة. لم يتم حذف أي شيء.': 'The confirmation phrase is wrong. Nothing was deleted.',
    'جميع الصفوف والبيانات المرتبطة بها': 'all grades and their data',
    'جميع حسابات المعلمين وتوزيعاتهم': 'all teacher accounts and their assignments',
    'تم نقل المادة بنجاح في الجدول الأساسي ✓': 'Subject moved in the master schedule ✓',
    'تم نقل بيانات الدرس بالكامل بنجاح (المادة + التحضير + الواجب) ✓': 'Lesson moved with its subject, topic and homework ✓',
    'تم نقل المادة وجميع بيانات الدروس بنجاح': 'Subject and all its lessons moved',
    'تم نقل بيانات الدرس بالكامل بنجاح (المادة + التحضير + الواجب)': 'Lesson moved with its subject, topic and homework',
    '(بدون اسم)': '(no name)',
    'تم إضافة الصف بنجاح': 'Grade added',
    'تم إضافة الفصل بنجاح': 'Class added',
    'تم تعديل اسم الصف بنجاح': 'Grade renamed',
    'تم تعديل اسم الفصل بنجاح': 'Class renamed',
    'تم حذف الصف بنجاح': 'Grade deleted',
    'تم حذف الفصل بنجاح': 'Class deleted',
    'تم تحديث القفل': 'Locks updated',
    'تم رفع الشعار': 'Logo uploaded',
    'تم حفظ التعديلات الأسبوعية بنجاح': 'Weekly changes saved',
    'تم الحفظ بنجاح — تم نشر المواد للأسابيع 1-19': 'Saved — subjects applied to weeks 1-19',
    'تم إلغاء العملية: تأكيد حذف جميع الصفوف غير صحيح': 'Cancelled: the confirmation to delete all grades was wrong',
    'تم إلغاء العملية: تأكيد حذف جميع حسابات المعلمين غير صحيح': 'Cancelled: the confirmation to delete all teachers was wrong',
    'لم يتم اختيار ملف': 'No file selected',
    'نوع غير معروف': 'Unknown type',
    'لم يتم العثور على فصول في الملف. تأكد أن العمود الأول يحتوي أسماء الفصول (مثل Grade 4 A) وأن صف العناوين يحتوي أسماء الأيام.': 'No classes were found in the file. Make sure the first column has class names (e.g. Grade 4 A) and the header row has day names.',
    'لا يمكن استخدام "admin" كاسم مستخدم للمعلم': '"admin" cannot be used as a teacher username',
    'لا يمكن استخدام "admin" كاسم مستخدم للمشرف': '"admin" cannot be used as a supervisor username'
  };

  /* ---------------------------------------------------------------------
     Patterns for text that contains numbers or names
     --------------------------------------------------------------------- */
  function t(s) { var r = translate(s); return r === null ? s : r; }
  function details(txt) {
    return txt
      .replace(/\((\S+) ح(\d+)\)/g, function (_, d, p) { return '(' + t(d) + ' P' + p + ')'; })
      .replace(/حذف الموضوع \(كان: /g, 'Topic removed (was: ')
      .replace(/حذف الواجب \(كان: /g, 'Homework removed (was: ')
      .replace(/(^|[|،,]\s*|:\s+)موضوع: /g, '$1Topic: ')
      .replace(/(^|[|،,]\s*|\s)واجب: /g, '$1Homework: ')
      .replace(/ و(\d+) أخرى$/, ' and $1 more')
      .replace(/، /g, ', ');
  }
  function who(n) { return t(n); }
  function days(list) { return list.split(/،\s*/).map(function (p) { return p.replace(/^(\S+)/, function (d) { return t(d); }); }).join(', '); }
  var P = [
    [/^الأسبوع\s+(\d+)\s*\((الحالي|الأحدث|غير معتمد)\)$/, function (m) { return 'Week ' + m[1] + ' (' + { 'الحالي': 'current', 'الأحدث': 'latest', 'غير معتمد': 'not approved' }[m[2]] + ')'; }],
    [/^(?:الأسبوع|أسبوع)\s+(\d+)$/, 'Week $1'],
    [/^الأسبوع الحالي:\s*(\d+)$/, 'Current week: $1'],
    [/^الأسبوع الدراسي:\s*(\d+)$/, 'School week: $1'],
    [/^متابعة الأسبوع\s+(\d+)$/, 'Week $1 follow-up'],
    [/^إحصائيات الإنجاز\s*—\s*الأسبوع\s*(\d+)$/, 'Completion statistics — week $1'],
    [/^(.+?)\s*·\s*الأسبوع\s+(\d+)$/, '$1 · Week $2'],
    [/^(?:ح|الحصة|حصة)\s*(\d+)$/, function (m) { return 'P' + m[1]; }],
    [/^ناقص\s+(\d+)\s+من\s+(\d+)\s+حصة$/, '$1 of $2 lessons missing'],
    [/^ناقص\s+(\d+)\s+من\s+(\d+)$/, '$1 of $2 missing'],
    [/^ناقص\s*\((\d+)\)\s*—\s*اضغط لفتح الجدول$/, 'Incomplete ($1) — tap to open'],
    [/^مكتمل\s*\((\d+)\)$/, 'Complete ($1)'],
    [/^قيد الانتظار\s*\((\d+)\)$/, 'Pending ($1)'],
    [/^مكتمل\s+(\d+)\s+من\s+(\d+)\s*·\s*النقص في:\s*(.+)$/, function (m) { return m[1] + ' of ' + m[2] + ' complete · missing on: ' + days(m[3]); }],
    [/^(\d+)\s+حصة مكتملة \(موضوع \+ واجب\)$/, '$1 lessons complete (topic + homework)'],
    [/^\((\d+)\s+حصة ✓\)$/, '($1 lessons ✓)'],
    [/^إنجاز الحصص\s*\((\d+)\s+من\s+(\d+)\)$/, 'Lessons done ($1 of $2)'],
    [/^نسبة الإنجاز\s+(\d+)%$/, 'Progress $1%'],
    [/^(\d+)\s+حصة ناقصة يوم\s+(\S+)$/, function (m) { return m[1] + ' missing on ' + t(m[2]); }],
    [/^(\S+)\s+ح(\d+)\s*·\s*(.+)$/, function (m) { return t(m[1]) + ' P' + m[2] + ' · ' + m[3]; }],
    [/^المعلمون المسجلون\s*\((\d+)\)$/, 'Registered teachers ($1)'],
    [/^المشرفون المسجلون\s*\((\d+)\)$/, 'Registered supervisors ($1)'],
    [/^تحديث حالة القفل للأسبوع\s+(\d+)$/, 'Update locks for week $1'],
    [/^(\d+)\s+حقل لم يُحفظ$/, '$1 unsaved fields'],
    [/^تم الحفظ\s*—\s*(\d+)\s+تعديل$/, 'Saved — $1 changes'],
    [/^تم الحفظ\s*\((\d+)\s+تعديل\)\s*✓?$/, 'Saved ($1 changes) ✓'],
    [/^✓?\s*تم حفظ\s+(\d+)\s+حصة للمعلم$/, '✓ $1 periods saved for the teacher'],
    [/^تم حفظ\s+(\d+)\s+حصة بنجاح$/, '$1 periods saved'],
    [/^جاري الرفع\.\.\.\s*(\d+)%$/, 'Uploading... $1%'],
    [/^حجم الملف أكبر من\s+(\d+)\s+ميجابايت$/, 'The file is larger than $1 MB'],
    [/^حذف الملف "(.+)"؟ لن يظهر للطلاب بعد الحذف\.$/, 'Delete "$1"? Students will no longer see it.'],
    [/^(\d+(?:\.\d+)?)\s*ك\.ب$/, '$1 KB'],
    [/^(\d+(?:\.\d+)?)\s*م\.ب$/, '$1 MB'],
    [/^محجوز لـ:\s*(.+)$/, 'Taken by: $1'],
    [/^معلم\s+(\d+)$/, 'Teacher $1'],
    [/^خطة الأسبوع\s+(\d+)\s+لم تُعتمد بعد$/, 'The plan for week $1 has not been approved yet'],
    [/^جاري تحضير خطة\s+(.+)، وسيتم نشرها هنا فور اعتمادها من إدارة المدرسة\.$/, 'The plan for $1 is being prepared and will appear here once the school approves it.'],
    [/^ستظهر خطة\s+(.+)\s+لهذا الأسبوع هنا فور اعتمادها من إدارة المدرسة\.$/, 'The plan for $1 will appear here once the school approves it.'],
    [/^الأسبوع\s+(\d+)\s+غير معتمد بعد، ولا يظهر لأولياء الأمور حتى يُعتمد من صفحة "متابعة الأسبوع"\.$/, 'Week $1 is not approved yet, so parents cannot see it until it is published from “Weekly follow-up”.'],
    [/^جدول الطالب\s*-\s*(.+)$/, 'Student timetable - $1'],
    [/^عرض الجداول\s*-\s*(.+)$/, 'Timetables - $1'],
    [/^سجل النشاطات\s*-\s*(.+)$/, 'Activity log - $1'],
    [/^اليوم:\s*(.+)$/, 'Today: $1'],
    [/^(.+?)\s*-\s*(\S+)\s+ح\s*(\d+)$/, function (m) { return m[1] + ' - ' + t(m[2]) + ' P' + m[3]; }],
    [/^موضوع الدرس\s*-\s*(.+)$/, 'Lesson topic - $1'],
    [/^الواجب\s*-\s*(.+)$/, 'Homework - $1'],
    [/^سيتم حذف\s+(.+)\s+نهائيًا\.\nاكتب "(.+)" للتأكيد:$/, function (m) { return 'This will permanently delete ' + t(m[1]) + '.\nType "' + m[2] + '" to confirm:'; }],

    /* flash messages from the server */
    [/^تم استيراد\s+(\d+)\s+فصل في\s+(\d+)\s+صف\s*—\s*(\d+)\s+حصة\s*\((\d+)\s+حصص يومياً\)، ونُشر الجدول في الأسابيع 1-19\.(?:\s*تم تحديث عدد الحصص اليومية في الإعدادات إلى\s+(\d+)\.)?$/,
      function (m) { return 'Imported ' + m[1] + ' classes in ' + m[2] + ' grades — ' + m[3] + ' lessons (' + m[4] + ' periods a day), applied to weeks 1-19.' + (m[5] ? ' Periods per day was updated to ' + m[5] + '.' : ''); }],
    [/^تنبيه: توجد صفوف قديمة من استيراد سابق بأسماء مكررة \((.+)\)\. احذفها من "إدارة الصفوف" إن لم تعد تحتاجها\.$/, 'Note: old grades from a previous import look duplicated ($1). Delete them in “Manage grades” if you no longer need them.'],
    [/^تم إضافة المعلم:\s*(.+)$/, 'Teacher added: $1'],
    [/^تم إضافة المشرف:\s*(.+)$/, 'Supervisor added: $1'],
    [/^تم حذف المعلم:\s*(.+)$/, 'Teacher deleted: $1'],
    [/^تم حذف المشرف:\s*(.+)$/, 'Supervisor deleted: $1'],
    [/^تم تفعيل حساب:\s*(.+)$/, 'Account enabled: $1'],
    [/^تم تعطيل حساب:\s*(.+)$/, 'Account disabled: $1'],
    [/^تم تغيير كلمة مرور:\s*(.+)$/, 'Password changed: $1'],
    [/^اسم المستخدم "(.+)" موجود بالفعل$/, 'The username "$1" already exists'],
    [/^تم إضافة\s+(\d+)\s+معلم، تم تخطي\s+(\d+)\s+\(موجودون مسبقاً\)$/, '$1 teachers added, $2 skipped (already exist)'],
    [/^تم حذف جميع الصفوف بنجاح\s*\((\d+)\s+صف\)$/, 'All grades deleted ($1)'],
    [/^تم حذف جميع حسابات المعلمين بنجاح\s*\((\d+)\s+حساب\)$/, 'All teacher accounts deleted ($1)'],
    [/^تم تعيين\s+(\d+)\s+خلية للمعلم\s+(.+)$/, '$1 periods assigned to $2'],
    [/^خطأ في قراءة الملف:\s*(.*)$/, 'Could not read the file: $1'],
    [/^خطأ غير متوقع:\s*(.*)$/, 'Unexpected error: $1'],
    [/^خطأ:\s*(.*)$/, 'Error: $1'],
    [/^✗\s*فشل الحفظ:\s*(.*)$/, '✗ Save failed: $1'],

    /* activity log records (stored in Arabic) */
    [/^تسجيل دخول المعلم:\s*(.+)$/, 'Teacher signed in: $1'],
    [/^تسجيل دخول المشرف:\s*(.+)$/, 'Supervisor signed in: $1'],
    [/^(.+?) عدّل (\d+) حصة — أسبوع (\d+) — (.+)$/, function (m) { return who(m[1]) + ' edited ' + m[2] + ' lessons — week ' + m[3] + ' — ' + m[4]; }],
    [/^(.+?) — فشل الحفظ — أسبوع (\d+) — (.+)$/, function (m) { return who(m[1]) + ' — save failed — week ' + m[2] + ' — ' + m[3]; }],
    [/^✓ تم الحفظ \| (.+?) \| أسبوع (\d+) \| (.+?) \| ([\s\S]+)$/, function (m) { return '✓ Saved | ' + who(m[1]) + ' | week ' + m[2] + ' | ' + m[3] + ' | ' + details(m[4]); }],
    [/^فشل DB commit \| (.+?) \| أسبوع (\d+) \| (.+?) \| ([\s\S]+)$/, function (m) { return 'DB commit failed | ' + who(m[1]) + ' | week ' + m[2] + ' | ' + m[3] + ' | ' + m[4]; }],
    [/^(.+?) (أرفق|استبدل) ملف "(.+)" — (\S+) ح(\d+) — أسبوع (\d+)$/, function (m) { return who(m[1]) + (m[2] === 'أرفق' ? ' attached ' : ' replaced ') + '"' + m[3] + '" — ' + t(m[4]) + ' P' + m[5] + ' — week ' + m[6]; }],
    [/^(.+?) حذف ملف "(.+)" — (\S+) ح(\d+) — أسبوع (\d+)$/, function (m) { return who(m[1]) + ' deleted "' + m[2] + '" — ' + t(m[3]) + ' P' + m[4] + ' — week ' + m[5]; }],
    [/^مرفق: (.+) \((\d+) KB\) \| (\S+) ح(\d+) \| أسبوع (\d+)$/, function (m) { return 'Attachment: ' + m[1] + ' (' + m[2] + ' KB) | ' + t(m[3]) + ' P' + m[4] + ' | week ' + m[5]; }],
    [/^استيراد الجدول المدرسي:\s*(\d+)\s+فصل$/, 'Timetable import: $1 classes'],
    [/^اعتماد جدول الأسبوع (\d+) لأولياء الأمور$/, 'Week $1 published to parents'],
    [/^تم اعتماد الجدول لـ (\d+) فصل من أصل (\d+)$/, 'Published for $1 of $2 classes'],
    [/^إضافة حساب معلم:\s*(.+)$/, 'Teacher account added: $1'],
    [/^إضافة حساب مشرف:\s*(.+)$/, 'Supervisor account added: $1'],
    [/^حذف حساب معلم:\s*(.+)$/, 'Teacher account deleted: $1'],
    [/^حذف حساب مشرف:\s*(.+)$/, 'Supervisor account deleted: $1'],
    [/^إعادة تعيين كلمة مرور المعلم:\s*(.+)$/, 'Teacher password reset: $1'],
    [/^إعادة تعيين كلمة مرور المشرف:\s*(.+)$/, 'Supervisor password reset: $1'],
    [/^إضافة صف جديد:\s*(.+)$/, 'Grade added: $1'],
    [/^إضافة فصل جديد:\s*(.+)$/, 'Class added: $1'],
    [/^حذف صف:\s*(.+?)(?: وجميع فصوله وبياناته)?$/, 'Grade deleted: $1'],
    [/^حذف فصل:\s*(.+?)(?: وجميع بياناته الأسبوعية)?$/, 'Class deleted: $1'],
    [/^تعديل اسم الصف من (.+) إلى (.+)$/, 'Grade renamed from $1 to $2'],
    [/^تعديل اسم الفصل من (.+) إلى (.+)$/, 'Class renamed from $1 to $2'],
    [/^تحديث توزيع مواد:\s*(.+) — (\d+) مادة$/, 'Assignments updated: $1 — $2 periods'],
    [/^حفظ الجدول الأساسي للفصل:?\s*(.+?)(?: — تم نشر المادة للأسابيع 1-19)?$/, 'Master schedule saved: $1'],
    [/^حذف جميع الصفوف \((\d+)\)$/, 'All grades deleted ($1)'],
    [/^حذف جميع حسابات المعلمين \((\d+)\)$/, 'All teacher accounts deleted ($1)'],
    [/^استيراد (\d+) حساب معلم من Excel$/, '$1 teacher accounts imported from Excel'],
    [/^نقل (?:مادة في الجدول الأساسي|درس أسبوعي)(?: مع التحضير والواجب)?:? (?:من )?(\S+) ح(\d+) (?:↔|إلى) (\S+) ح(\d+)(?: \(أسبوع (\d+)\))?$/,
      function (m) { return 'Moved ' + t(m[1]) + ' P' + m[2] + ' ↔ ' + t(m[3]) + ' P' + m[4] + (m[5] ? ' (week ' + m[5] + ')' : ''); }],
    [/^فصل (\d+)$/, 'Class $1'],
    [/^الحد الأقصى (\d+) روابط للحصة$/, 'Up to $1 links per lesson'],
    [/^(.+?) أضاف رابط "(.+)" — (\S+) ح(\d+) — أسبوع (\d+)$/, function (m) { return who(m[1]) + ' added link "' + t(m[2]) + '" — ' + t(m[3]) + ' P' + m[4] + ' — week ' + m[5]; }],
    [/^(.+?) حذف رابط "(.+)" — (\S+) ح(\d+) — أسبوع (\d+)$/, function (m) { return who(m[1]) + ' removed link "' + t(m[2]) + '" — ' + t(m[3]) + ' P' + m[4] + ' — week ' + m[5]; }],
    [/^رابط: (.+)$/, 'Link: $1'],
    [/^✓ تم الحفظ \| (.+?) \| أسبوع (\d+) \| (.*)$/, function (m) { return '✓ Saved | ' + who(m[1]) + ' | week ' + m[2] + ' | ' + details(m[3]); }]
  ];

  /* ---------------------------------------------------------------------
     Translation core
     --------------------------------------------------------------------- */
  function norm(s) { return String(s).replace(/\s+/g, ' ').trim(); }

  function names(text) {
    var out = text, changed = false;
    Object.keys(NAMES).forEach(function (ar) {
      if (ar && NAMES[ar] && out.indexOf(ar) !== -1) { out = out.split(ar).join(NAMES[ar]); changed = true; }
    });
    return changed ? out : null;
  }

  function translate(src) {
    if (src == null) return null;
    var s = String(src);
    if (!AR.test(s)) return null;
    var r = translateOne(s.indexOf('\nاكتب "') !== -1 ? s.trim() : norm(s));
    if (r !== null) return names(r) || r;
    if (s.indexOf('\n') !== -1) {                                   // multi-line dialogs
      var any = false;
      var out = s.split('\n').map(function (l) { var x = translate(l); if (x !== null) any = true; return x === null ? l : x; });
      if (any) return out.join('\n');
    }
    return names(norm(s));
  }

  function translateOne(k) {
    if (Object.prototype.hasOwnProperty.call(DICT, k)) return DICT[k];
    for (var i = 0; i < P.length; i++) {
      var m = k.match(P[i][0]);
      if (m) return typeof P[i][1] === 'function' ? P[i][1](m) : k.replace(P[i][0], P[i][1]);
    }
    // Decorations around a known phrase: "📝 …", "✓ …", "…:", "… ✓", "(…)"
    var d = k.match(/^([✓✗📝🔒📎📚📖•\-–—→←]\s*)?(.+?)(\s*[:：]|\s*✓|\s*\.\.\.|\.)?$/);
    if (d && d[2] !== k && DICT[d[2]]) return (d[1] || '') + DICT[d[2]] + (d[3] || '');
    // Composite text: translate every Arabic piece between separators
    if (/ — | · |، | \| /.test(k)) {
      var ok = true;
      var parts = k.split(/( — | · |، | \| )/).map(function (part) {
        if (/^( — | · |، | \| )$/.test(part) || !AR.test(part)) return part === '، ' ? ', ' : part;
        var x = translateOne(part);
        if (x === null) ok = false;
        return x === null ? part : x;
      });
      if (ok) return parts.join('');
    }
    return null;
  }

  /* ---------------------------------------------------------------------
     DOM application (text nodes + attributes), reversible
     --------------------------------------------------------------------- */
  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt', 'data-label', 'data-empty'];
  var SKIP = 'script,style,textarea,noscript,[translate="no"],.notranslate';   // content never translated
  var NO_TRANSLATE = '[translate="no"],.notranslate';                      // nothing translated, not even attributes
  var origText = new WeakMap(), lastText = new WeakMap(), attrState = new WeakMap();
  var lang = 'ar';

  function skipped(el) { return !el || (el.closest && el.closest(SKIP)); }

  function textNode(node) {
    var cur = node.nodeValue;
    var host = node.parentElement;
    if (host && host.hasAttribute('data-en') && host.childNodes.length === 1) {
      if (!host.hasAttribute('data-ar')) host.setAttribute('data-ar', cur.trim());
      var want = lang === 'en' ? host.getAttribute('data-en') : host.getAttribute('data-ar');
      if (cur.trim() !== want) node.nodeValue = want;
      lastText.set(node, node.nodeValue);
      return;
    }
    var ours = lastText.has(node) && lastText.get(node) === cur;
    var source = ours && origText.has(node) ? origText.get(node) : cur;
    if (!ours) origText.delete(node);
    if (lang === 'en') {
      var r = translate(source);
      if (r !== null) {
        var out = source.match(/^\s*/)[0] + r + source.match(/\s*$/)[0];
        origText.set(node, source);
        if (node.nodeValue !== out) node.nodeValue = out;
        lastText.set(node, out);
        return;
      }
    } else if (origText.has(node) && ours) {
      if (node.nodeValue !== source) node.nodeValue = source;   // never write an unchanged value (it would re-trigger the observer)
      origText.delete(node);
    }
    lastText.set(node, node.nodeValue);
  }

  function attrs(el) {
    var state = attrState.get(el) || {};
    ATTRS.forEach(function (a) {
      if (!el.hasAttribute(a)) return;
      var cur = el.getAttribute(a), st = state[a];
      var ours = st && st.last === cur;
      var source = ours ? st.orig : cur;
      var val = source;
      if (lang === 'en') { var r = translate(source); if (r !== null) val = r; }
      if (val !== cur) el.setAttribute(a, val);
      state[a] = { orig: source, last: val };
    });
    // button-like inputs show their value
    if (el.tagName === 'INPUT' && /^(submit|button|reset)$/i.test(el.type)) {
      var v = state.value, curV = el.value, oursV = v && v.last === curV, srcV = oursV ? v.orig : curV;
      var outV = lang === 'en' ? (translate(srcV) || srcV) : srcV;
      if (outV !== curV) el.value = outV;
      state.value = { orig: srcV, last: outV };
    }
    attrState.set(el, state);
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!skipped(root.parentElement)) textNode(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1 && skipped(root)) return;
    if (root.nodeType === 1) attrs(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (n.nodeType === 1) {
          if (n.matches(SKIP)) {
            if (!n.closest(NO_TRANSLATE) && n.tagName === 'TEXTAREA') attrs(n);   // placeholder yes, typed text no
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) textNode(n); else attrs(n); }
  }

  var titleOrig = null, titleLast = null;
  function title() {
    if (titleOrig === null || document.title !== titleLast) titleOrig = document.title;
    var out = lang === 'en' ? (translate(titleOrig) || titleOrig) : titleOrig;
    if (document.title !== out) document.title = out;
    titleLast = out;
  }

  /* ---------------------------------------------------------------------
     Language switch
     --------------------------------------------------------------------- */
  function readStored() {
    try {
      var q = new URLSearchParams(location.search).get('lang');
      if (q === 'en' || q === 'ar') return q;
      return localStorage.getItem(STORE_KEY) || localStorage.getItem('admin-language') || localStorage.getItem('student-language') || 'ar';
    } catch (e) { return 'ar'; }
  }

  function setDir(l) {
    var h = document.documentElement;
    h.lang = l; h.dir = l === 'en' ? 'ltr' : 'rtl';
  }

  function setLanguage(l, silent) {
    lang = l === 'en' ? 'en' : 'ar';
    setDir(lang);
    try { localStorage.setItem(STORE_KEY, lang); } catch (e) {}
    try { document.cookie = 'site_lang=' + lang + ';path=/;max-age=31536000;samesite=lax'; } catch (e) {}
    if (document.body) {
      document.body.dataset.language = lang;
      walk(document.body);
      title();
      document.querySelectorAll('[data-lang-option]').forEach(function (b) {
        var on = b.getAttribute('data-lang-option') === lang;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', String(on));
      });
    }
    document.documentElement.removeAttribute('data-i18n-pending');
    if (!silent) {
      document.dispatchEvent(new CustomEvent('site-language-change', { detail: { lang: lang } }));
      document.dispatchEvent(new CustomEvent('student-language-change', { detail: { lang: lang } }));
    }
  }

  function switchMarkup() {
    return '<div class="i18n-switch" role="group" aria-label="اختيار اللغة">' +
      '<button type="button" data-lang-option="ar" lang="ar">العربية</button>' +
      '<button type="button" data-lang-option="en" lang="en">English</button></div>';
  }

  function injectSwitch() {
    if (document.querySelector('[data-lang-option]')) return;
    var slot = document.querySelector('[data-lang-slot]') || document.querySelector('.topbar-actions');
    if (slot) { slot.insertAdjacentHTML(slot.hasAttribute('data-lang-slot') ? 'beforeend' : 'afterbegin', switchMarkup()); return; }
    var holder = document.createElement('div');
    holder.className = 'i18n-float';
    holder.innerHTML = switchMarkup();
    document.body.appendChild(holder);
  }

  var css = '.i18n-switch{display:inline-flex;direction:ltr;gap:2px;padding:3px;background:#fff;border:1px solid #d9e2de;border-radius:999px;font-family:inherit}' +
    '.i18n-switch button{border:0;background:none;padding:.3rem .8rem;border-radius:999px;font:700 .8rem/1.4 inherit;font-family:inherit;color:#5d6e6a;cursor:pointer;min-height:32px}' +
    '.i18n-switch button.active{background:#0e3b37;color:#fff}' +
    '.i18n-float{position:fixed;top:12px;inset-inline-end:12px;z-index:9999;box-shadow:0 6px 20px rgba(14,59,55,.15);border-radius:999px}' +
    'html[data-i18n-pending] body{visibility:hidden}';

  /* ---------------------------------------------------------------------
     Boot: set direction immediately (no flash), translate once the DOM exists
     --------------------------------------------------------------------- */
  lang = readStored() === 'en' ? 'en' : 'ar';
  setDir(lang);
  if (lang === 'en') document.documentElement.setAttribute('data-i18n-pending', '');
  var style = document.createElement('style'); style.textContent = css;
  (document.head || document.documentElement).appendChild(style);
  setTimeout(function () { document.documentElement.removeAttribute('data-i18n-pending'); }, 1500); // never stay hidden

  // Dialogs follow the language too
  ['alert', 'confirm', 'prompt'].forEach(function (fn) {
    var orig = window[fn];
    if (typeof orig !== 'function') return;
    window[fn] = function (msg) {
      var args = Array.prototype.slice.call(arguments);
      if (lang === 'en' && typeof msg === 'string') args[0] = translate(msg) || msg;
      return orig.apply(window, args);
    };
  });

  function boot() {
    injectSwitch();
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-lang-option]');
      if (b) { e.preventDefault(); setLanguage(b.getAttribute('data-lang-option')); }
    });
    setLanguage(lang);          // also tells page scripts (dates, labels) to render once
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        if (r.type === 'childList') r.addedNodes.forEach(walk);
        else if (r.type === 'characterData') { if (!skipped(r.target.parentElement)) textNode(r.target); }
        else if (r.type === 'attributes' && !(r.target.closest && r.target.closest(NO_TRANSLATE))) attrs(r.target);
      });
      if (document.title !== titleLast) title();
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS.concat(['value']) });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

  window.I18N = {
    t: function (s) { return lang === 'en' ? (translate(s) || s) : s; },
    translate: translate,
    set: setLanguage,
    get lang() { return lang; },
    apply: function (root) { walk(root || document.body); }
  };
  window.applyDashboardLanguage = function () { walk(document.body); };
})();
