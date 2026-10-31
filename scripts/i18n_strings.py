"""Interface translations: English -> Hindi, Arabic.

Single source of truth for the language packs. Run

    python scripts/i18n_strings.py

to regenerate src/job_hunting_agent/static/ui/i18n/{hi,ar}.js. Keys are the
exact English text a page shows (whitespace collapsed). Job data, resumes,
questions and AI feedback are content, not interface, and stay in English.

Rows are tab separated: English<TAB>Hindi<TAB>Arabic.
"""

from __future__ import annotations

import json
from pathlib import Path

STRINGS = r"""
Job Hunting Agent	जॉब हंटिंग एजेंट	وكيل البحث عن عمل
Resume to offer	रिज़्यूमे से ऑफ़र तक	من السيرة الذاتية إلى العرض
Skip to content	सामग्री पर जाएँ	انتقل إلى المحتوى
Main navigation	मुख्य नेविगेशन	التنقل الرئيسي
Open navigation	नेविगेशन खोलें	فتح التنقل
Workspace	वर्कस्पेस	مساحة العمل
Practice	अभ्यास	التدريب
Account	खाता	الحساب
Overview	अवलोकन	نظرة عامة
Run & profile	रन और प्रोफ़ाइल	التشغيل والملف الشخصي
Run and profile	रन और प्रोफ़ाइल	التشغيل والملف الشخصي
Job leads	जॉब लीड्स	فرص العمل
Resume & ATS	रिज़्यूमे और ATS	السيرة الذاتية وATS
Resume and ATS	रिज़्यूमे और ATS	السيرة الذاتية وATS
Approvals	स्वीकृतियाँ	الموافقات
Mock Test	मॉक टेस्ट	اختبار تجريبي
Mock Interview	मॉक इंटरव्यू	مقابلة تجريبية
Progress reports	प्रगति रिपोर्ट	تقارير التقدم
Progress Reports	प्रगति रिपोर्ट	تقارير التقدم
Privacy & my data	गोपनीयता और मेरा डेटा	الخصوصية وبياناتي
Admin metrics	एडमिन मेट्रिक्स	مقاييس المسؤول
Dashboard	डैशबोर्ड	لوحة التحكم
Sign out	साइन आउट	تسجيل الخروج
Sign in	साइन इन	تسجيل الدخول
Language	भाषा	اللغة
Run agent	एजेंट चलाएँ	تشغيل الوكيل
Switch to light theme	लाइट थीम पर जाएँ	التبديل إلى المظهر الفاتح
Switch to dark theme	डार्क थीम पर जाएँ	التبديل إلى المظهر الداكن
Light theme	लाइट थीम	المظهر الفاتح
Dark theme	डार्क थीम	المظهر الداكن
Dismiss	बंद करें	إغلاق
Close	बंद करें	إغلاق
Loading…	लोड हो रहा है…	جارٍ التحميل…
Request failed.	अनुरोध विफल रहा।	فشل الطلب.
Welcome	स्वागत है	مرحبًا
Good morning	सुप्रभात	صباح الخير
Good afternoon	नमस्कार	مساء الخير
Good evening	शुभ संध्या	مساء الخير
No ATS score yet	अभी कोई ATS स्कोर नहीं	لا توجد درجة ATS بعد
No score yet	अभी कोई स्कोर नहीं	لا توجد درجة بعد
ATS score	ATS स्कोर	درجة ATS
of 100	100 में से	من 100
Upload your resume to get an ATS score, matched job leads, a tailored resume for every lead and recruiter-ready drafts.	ATS स्कोर, मेल खाती जॉब लीड्स, हर लीड के लिए अनुकूलित रिज़्यूमे और रिक्रूटर के लिए तैयार ड्राफ़्ट पाने के लिए अपना रिज़्यूमे अपलोड करें।	ارفع سيرتك الذاتية لتحصل على درجة ATS وفرص عمل مطابقة وسيرة ذاتية مخصصة لكل فرصة ومسودات جاهزة لمسؤولي التوظيف.
Upload resume and run	रिज़्यूमे अपलोड करें और चलाएँ	ارفع السيرة الذاتية وشغّل
Run again	फिर से चलाएँ	التشغيل مجددًا
View job leads	जॉब लीड्स देखें	عرض فرص العمل
Latest run	नवीनतम रन	آخر تشغيل
Job leads in the latest run	नवीनतम रन में जॉब लीड्स	فرص العمل في آخر تشغيل
Strong matches (70% and up)	मज़बूत मिलान (70% और ऊपर)	تطابقات قوية (70% فأكثر)
Drafts ready	तैयार ड्राफ़्ट	مسودات جاهزة
Emails waiting for approval	स्वीकृति की प्रतीक्षा में ईमेल	رسائل بانتظار الموافقة
Next best actions	अगले सबसे अच्छे कदम	أفضل الخطوات التالية
Top matches	सबसे अच्छे मिलान	أفضل التطابقات
All leads	सभी लीड्स	كل الفرص
Open	खोलें	فتح
Job sources	जॉब स्रोत	مصادر الوظائف
Job sources active	सक्रिय जॉब स्रोत	مصادر وظائف نشطة
Daily automation	दैनिक ऑटोमेशन	الأتمتة اليومية
Change	बदलें	تغيير
Scheduled	शेड्यूल किया गया	مجدول
Off	बंद	متوقف
Last run failed	पिछला रन विफल रहा	فشل آخر تشغيل
Set a daily time on Run & profile to get fresh leads every day.	हर दिन नई लीड्स पाने के लिए रन और प्रोफ़ाइल में दैनिक समय सेट करें।	حدّد وقتًا يوميًا في التشغيل والملف الشخصي لتحصل على فرص جديدة كل يوم.
No leads yet	अभी कोई लीड नहीं	لا توجد فرص بعد
Run the agent to see your best matches here.	अपने सबसे अच्छे मिलान यहाँ देखने के लिए एजेंट चलाएँ।	شغّل الوكيل لترى أفضل التطابقات هنا.
Start a run	रन शुरू करें	ابدأ تشغيلًا
Accept the privacy notice	गोपनीयता सूचना स्वीकार करें	اقبل إشعار الخصوصية
Runs need your consent before your resume is processed.	आपके रिज़्यूमे को प्रोसेस करने से पहले आपकी सहमति ज़रूरी है।	تحتاج عمليات التشغيل إلى موافقتك قبل معالجة سيرتك الذاتية.
Review notice	सूचना देखें	مراجعة الإشعار
Nothing reaches a recruiter until you approve it.	आपकी स्वीकृति के बिना कुछ भी रिक्रूटर तक नहीं पहुँचता।	لا يصل شيء إلى مسؤول التوظيف حتى توافق عليه.
Review	देखें	مراجعة
See fixes	सुधार देखें	عرض التحسينات
Schedule a daily run	दैनिक रन शेड्यूल करें	جدولة تشغيل يومي
Fresh leads and drafts every day at a time you choose.	आपके चुने समय पर हर दिन नई लीड्स और ड्राफ़्ट।	فرص ومسودات جديدة كل يوم في الوقت الذي تختاره.
Schedule	शेड्यूल करें	جدولة
Rate a few leads	कुछ लीड्स को रेट करें	قيّم بعض الفرص
Marking leads relevant or not sharpens your matches.	लीड्स को प्रासंगिक या अप्रासंगिक चिह्नित करने से आपके मिलान बेहतर होते हैं।	تحديد الفرص المناسبة وغير المناسبة يحسّن تطابقاتك.
Rate leads	लीड्स रेट करें	تقييم الفرص
Upload your resume and run the agent	अपना रिज़्यूमे अपलोड करें और एजेंट चलाएँ	ارفع سيرتك الذاتية وشغّل الوكيل
It scores your resume and finds matching jobs in about a minute.	यह लगभग एक मिनट में आपके रिज़्यूमे को स्कोर करता है और मेल खाती नौकरियाँ ढूँढता है।	يقيّم سيرتك الذاتية ويجد الوظائف المطابقة في نحو دقيقة.
Top match	सबसे अच्छा मिलान	أفضل تطابق
Run the agent	एजेंट चलाएँ	شغّل الوكيل
Your resume and search settings. Run once now, or schedule a daily run that finds fresh leads and drafts automatically.	आपका रिज़्यूमे और खोज सेटिंग्स। अभी एक बार चलाएँ, या दैनिक रन शेड्यूल करें जो अपने-आप नई लीड्स और ड्राफ़्ट ढूँढे।	سيرتك الذاتية وإعدادات البحث. شغّل مرة الآن، أو جدول تشغيلًا يوميًا يجد فرصًا ومسودات جديدة تلقائيًا.
Resume	रिज़्यूमे	السيرة الذاتية
Drop your resume here or choose a file	अपना रिज़्यूमे यहाँ छोड़ें या फ़ाइल चुनें	أفلت سيرتك الذاتية هنا أو اختر ملفًا
PDF, DOCX, TXT or Markdown	PDF, DOCX, TXT या Markdown	PDF أو DOCX أو TXT أو Markdown
No resume saved yet. Upload one for your first run.	अभी कोई रिज़्यूमे सेव नहीं है। पहले रन के लिए एक अपलोड करें।	لا توجد سيرة ذاتية محفوظة بعد. ارفع واحدة لأول تشغيل.
Candidate	उम्मीदवार	المرشح
Name	नाम	الاسم
Phone	फ़ोन	الهاتف
Email	ईमेल	البريد الإلكتروني
LinkedIn profile URL	LinkedIn प्रोफ़ाइल URL	رابط ملف LinkedIn
Naukri profile URL	Naukri प्रोफ़ाइल URL	رابط ملف Naukri
Optional	वैकल्पिक	اختياري
These links are added to your recruiter email drafts so recruiters can view your profiles. Your LinkedIn link is also used on the ATS resume if your uploaded resume has no contact details. They are not used to sign in to or search LinkedIn or Naukri; jobs are found from your target roles, skills, locations and experience.	ये लिंक आपके रिक्रूटर ईमेल ड्राफ़्ट में जोड़े जाते हैं ताकि रिक्रूटर आपकी प्रोफ़ाइल देख सकें। अगर अपलोड किए रिज़्यूमे में संपर्क विवरण नहीं है, तो LinkedIn लिंक ATS रिज़्यूमे में भी जोड़ा जाता है। इनसे LinkedIn या Naukri में साइन इन या खोज नहीं की जाती; नौकरियाँ आपकी लक्षित भूमिकाओं, कौशल, स्थानों और अनुभव से ढूँढी जाती हैं।	تُضاف هذه الروابط إلى مسودات رسائلك لمسؤولي التوظيف ليتمكنوا من رؤية ملفاتك. ويُستخدم رابط LinkedIn أيضًا في سيرة ATS إذا لم تتضمن سيرتك المرفوعة بيانات اتصال. لا تُستخدم لتسجيل الدخول إلى LinkedIn أو Naukri أو البحث فيهما؛ فالوظائف تُوجد من الأدوار المستهدفة والمهارات والمواقع والخبرة.
Search	खोज	البحث
Target roles	लक्षित भूमिकाएँ	الأدوار المستهدفة
Comma separated, for example Data Engineer, Analytics Engineer	कॉमा से अलग करें, जैसे Data Engineer, Analytics Engineer	مفصولة بفواصل، مثل Data Engineer, Analytics Engineer
Locations	स्थान	المواقع
Skills	कौशल	المهارات
Experience (years)	अनुभव (वर्ष)	الخبرة (بالسنوات)
Max jobs per source	प्रति स्रोत अधिकतम नौकरियाँ	الحد الأقصى للوظائف لكل مصدر
Application mode	आवेदन मोड	وضع التقديم
Draft only	केवल ड्राफ़्ट	مسودة فقط
Email recruiters after my approval	मेरी स्वीकृति के बाद रिक्रूटर को ईमेल करें	راسل مسؤولي التوظيف بعد موافقتي
Enter 0 if you are a fresher. Experience sets portal filters; it never adds experience to your ATS report or resume.	फ्रेशर हैं तो 0 लिखें। अनुभव से पोर्टल फ़िल्टर तय होते हैं; यह आपकी ATS रिपोर्ट या रिज़्यूमे में अनुभव नहीं जोड़ता।	أدخل 0 إذا كنت حديث التخرج. تضبط الخبرة فلاتر البوابات؛ ولا تضيف أي خبرة إلى تقرير ATS أو سيرتك الذاتية.
Job description	जॉब विवरण	الوصف الوظيفي
Optional. Paste one to check keywords, required skills and screening risks.	वैकल्पिक। कीवर्ड, ज़रूरी कौशल और स्क्रीनिंग जोखिम जाँचने के लिए एक पेस्ट करें।	اختياري. الصق وصفًا لفحص الكلمات المفتاحية والمهارات المطلوبة ومخاطر الفرز.
Paste the target job description	लक्षित जॉब विवरण पेस्ट करें	الصق الوصف الوظيفي المستهدف
Daily time	दैनिक समय	الوقت اليومي
Needed for Schedule Daily Run	दैनिक रन शेड्यूल करने के लिए ज़रूरी	مطلوب لجدولة التشغيل اليومي
Schedule Daily Run saves this resume and runs the agent every day at this time in your browser's timezone. Schedules survive server restarts.	दैनिक रन शेड्यूल करने पर यह रिज़्यूमे सेव होता है और एजेंट हर दिन इस समय आपके ब्राउज़र के टाइमज़ोन में चलता है। सर्वर रीस्टार्ट होने पर भी शेड्यूल बना रहता है।	تحفظ جدولة التشغيل اليومي هذه السيرة الذاتية وتشغّل الوكيل كل يوم في هذا الوقت حسب المنطقة الزمنية لمتصفحك. وتبقى الجداول بعد إعادة تشغيل الخادم.
Schedule Daily Run	दैनिक रन शेड्यूल करें	جدولة التشغيل اليومي
Stop Daily Run	दैनिक रन रोकें	إيقاف التشغيل اليومي
Run progress	रन की प्रगति	تقدّم التشغيل
Nothing is sent without you. In Email mode each recruiter email waits in Approvals: review, edit, approve, and you still have a short undo window. Daily limits stop accidental mass emails.	आपके बिना कुछ नहीं भेजा जाता। ईमेल मोड में हर रिक्रूटर ईमेल स्वीकृतियों में रुकता है: देखें, बदलें, स्वीकृत करें, और फिर भी थोड़े समय तक पूर्ववत कर सकते हैं। दैनिक सीमाएँ गलती से बहुत सारे ईमेल जाने से रोकती हैं।	لا يُرسل شيء بدونك. في وضع البريد تنتظر كل رسالة في الموافقات: راجع، عدّل، وافق، ويبقى لديك وقت قصير للتراجع. وتمنع الحدود اليومية الإرسال الجماعي عن طريق الخطأ.
Fill in the required details	ज़रूरी विवरण भरें	أكمل البيانات المطلوبة
The agent can run once these are complete:	ये पूरे होने के बाद एजेंट चल सकता है:	يمكن تشغيل الوكيل بعد إكمال ما يلي:
Fill in now	अभी भरें	أكمل الآن
Upload your resume	अपना रिज़्यूमे अपलोड करें	ارفع سيرتك الذاتية
Privacy notice consent	गोपनीयता सूचना की सहमति	الموافقة على إشعار الخصوصية
Accept the privacy notice to continue	जारी रखने के लिए गोपनीयता सूचना स्वीकार करें	اقبل إشعار الخصوصية للمتابعة
Enter a valid phone number (7 to 15 digits, for example +91 98765 43210)	मान्य फ़ोन नंबर दर्ज करें (7 से 15 अंक, जैसे +91 98765 43210)	أدخل رقم هاتف صحيحًا (من 7 إلى 15 رقمًا، مثل +91 98765 43210)
Enter a valid phone number (7 to 15 digits, for example +91 98765 43210).	मान्य फ़ोन नंबर दर्ज करें (7 से 15 अंक, जैसे +91 98765 43210)।	أدخل رقم هاتف صحيحًا (من 7 إلى 15 رقمًا، مثل +91 98765 43210).
Experience (years) must be a number from 0 to 50	अनुभव (वर्ष) 0 से 50 के बीच की संख्या होनी चाहिए	يجب أن تكون الخبرة (بالسنوات) رقمًا من 0 إلى 50
Experience (years) must be a number from 0 to 50.	अनुभव (वर्ष) 0 से 50 के बीच की संख्या होनी चाहिए।	يجب أن تكون الخبرة (بالسنوات) رقمًا من 0 إلى 50.
Max jobs per source must be from 1 to 50	प्रति स्रोत अधिकतम नौकरियाँ 1 से 50 के बीच होनी चाहिए	يجب أن يكون الحد الأقصى للوظائف لكل مصدر من 1 إلى 50
Max jobs per source must be from 1 to 50.	प्रति स्रोत अधिकतम नौकरियाँ 1 से 50 के बीच होनी चाहिए।	يجب أن يكون الحد الأقصى للوظائف لكل مصدر من 1 إلى 50.
Daily time is required to schedule a daily run	दैनिक रन शेड्यूल करने के लिए दैनिक समय ज़रूरी है	الوقت اليومي مطلوب لجدولة تشغيل يومي
Daily time is required to schedule the agent.	एजेंट शेड्यूल करने के लिए दैनिक समय ज़रूरी है।	الوقت اليومي مطلوب لجدولة الوكيل.
Upload a resume before running or scheduling the agent.	एजेंट चलाने या शेड्यूल करने से पहले रिज़्यूमे अपलोड करें।	ارفع سيرة ذاتية قبل تشغيل الوكيل أو جدولته.
Upload a PDF, DOCX, TXT, or MD resume.	PDF, DOCX, TXT या MD रिज़्यूमे अपलोड करें।	ارفع سيرة ذاتية بصيغة PDF أو DOCX أو TXT أو MD.
Please accept the privacy notice before uploading or processing your resume.	रिज़्यूमे अपलोड या प्रोसेस करने से पहले कृपया गोपनीयता सूचना स्वीकार करें।	يرجى قبول إشعار الخصوصية قبل رفع سيرتك الذاتية أو معالجتها.
Running…	चल रहा है…	قيد التشغيل…
Scoring your resume	आपके रिज़्यूमे को स्कोर किया जा रहा है	تقييم سيرتك الذاتية
Searching LinkedIn, Naukri and job boards	LinkedIn, Naukri और जॉब बोर्ड में खोज जारी है	البحث في LinkedIn وNaukri ومواقع الوظائف
Ranking jobs and preparing application drafts	नौकरियों की रैंकिंग और आवेदन ड्राफ़्ट तैयार किए जा रहे हैं	ترتيب الوظائف وإعداد مسودات التقديم
Results ready	परिणाम तैयार	النتائج جاهزة
Run failed.	रन विफल रहा।	فشل التشغيل.
Run failed. Check the server log and try again.	रन विफल रहा। सर्वर लॉग देखें और फिर कोशिश करें।	فشل التشغيل. تحقق من سجل الخادم وحاول مجددًا.
Schedule failed.	शेड्यूल विफल रहा।	فشلت الجدولة.
Scheduling failed.	शेड्यूल करना विफल रहा।	فشلت الجدولة.
Daily run stopped.	दैनिक रन रोक दिया गया।	تم إيقاف التشغيل اليومي.
The daily run is still active.	दैनिक रन अभी भी सक्रिय है।	التشغيل اليومي لا يزال نشطًا.
Timezone	टाइमज़ोन	المنطقة الزمنية
Next run	अगला रन	التشغيل التالي
Last run	पिछला रन	آخر تشغيل
Not set	सेट नहीं	غير محدد
Not scheduled	शेड्यूल नहीं	غير مجدول
No run yet	अभी कोई रन नहीं	لا يوجد تشغيل بعد
Individual postings matched by role, skills and location. Experience is checked when a posting states it; otherwise it is marked unverified for your review.	भूमिका, कौशल और स्थान से मेल खाती अलग-अलग पोस्टिंग। पोस्टिंग में अनुभव लिखा हो तो उसकी जाँच होती है; नहीं तो उसे आपकी समीक्षा के लिए असत्यापित चिह्नित किया जाता है।	إعلانات فردية مطابقة حسب الدور والمهارات والموقع. تُفحص الخبرة عندما يذكرها الإعلان؛ وإلا تُعلَّم بأنها غير مؤكدة لمراجعتك.
Layout	लेआउट	التخطيط
List	सूची	قائمة
Table	तालिका	جدول
Title, company, skill or location	पद, कंपनी, कौशल या स्थान	المسمى أو الشركة أو المهارة أو الموقع
Source	स्रोत	المصدر
All sources	सभी स्रोत	كل المصادر
Minimum match	न्यूनतम मिलान	الحد الأدنى للتطابق
Sort	क्रम	الترتيب
Best match	सबसे अच्छा मिलान	الأفضل تطابقًا
Newest	सबसे नया	الأحدث
Company A to Z	कंपनी A से Z	الشركة من A إلى Z
Open job	जॉब खोलें	فتح الوظيفة
(opens in a new tab)	(नए टैब में खुलता है)	(يفتح في علامة تبويب جديدة)
Prepare tailored resume	अनुकूलित रिज़्यूमे तैयार करें	إعداد سيرة ذاتية مخصصة
Preparing resume…	रिज़्यूमे तैयार हो रहा है…	جارٍ إعداد السيرة الذاتية…
Retry tailored resume	अनुकूलित रिज़्यूमे फिर से आज़माएँ	إعادة محاولة السيرة المخصصة
Tailored resume	अनुकूलित रिज़्यूमे	سيرة ذاتية مخصصة
What changed in this resume	इस रिज़्यूमे में क्या बदला	ما الذي تغيّر في هذه السيرة
Relevant	प्रासंगिक	مناسبة
Not relevant…	प्रासंगिक नहीं…	غير مناسبة…
Saved	सेव हुआ	تم الحفظ
Saving…	सेव हो रहा है…	جارٍ الحفظ…
Saved. Thanks, this improves your matches.	सेव हुआ। धन्यवाद, इससे आपके मिलान बेहतर होंगे।	تم الحفظ. شكرًا، هذا يحسّن تطابقاتك.
Could not save.	सेव नहीं हो सका।	تعذّر الحفظ.
Wrong role	गलत भूमिका	دور غير مناسب
Wrong location	गलत स्थान	موقع غير مناسب
Wrong seniority	गलत वरिष्ठता स्तर	مستوى أقدمية غير مناسب
Skills do not match	कौशल मेल नहीं खाते	المهارات غير متطابقة
Salary	वेतन	الراتب
Company	कंपनी	الشركة
Duplicate	डुप्लिकेट	مكررة
Expired / closed	समाप्त / बंद	منتهية / مغلقة
Other	अन्य	أخرى
Matched	मेल खाते	متطابقة
Missing	कमी	ناقصة
Additional Skills	अतिरिक्त कौशल	مهارات إضافية
No source-backed additions	स्रोत-समर्थित कोई जोड़ नहीं	لا إضافات مدعومة بمصدر
All supported job skills are already listed	जॉब के सभी समर्थित कौशल पहले से सूचीबद्ध हैं	كل مهارات الوظيفة المدعومة مدرجة بالفعل
No resume evidence for the remaining job skills	बाकी जॉब कौशल के लिए रिज़्यूमे में कोई प्रमाण नहीं	لا دليل في السيرة على مهارات الوظيفة المتبقية
No specific skills found in this posting	इस पोस्टिंग में कोई विशेष कौशल नहीं मिला	لم يُعثر على مهارات محددة في هذا الإعلان
Description unavailable, check the posting	विवरण उपलब्ध नहीं, पोस्टिंग देखें	الوصف غير متاح، راجع الإعلان
Validated API	सत्यापित API	واجهة API موثّقة
Public discovery	सार्वजनिक खोज	اكتشاف عام
Job board	जॉब बोर्ड	موقع وظائف
Entry level	एंट्री लेवल	مستوى مبتدئ
Experience not stated	अनुभव नहीं बताया गया	الخبرة غير مذكورة
date verified	तारीख सत्यापित	التاريخ مؤكد
date unverified	तारीख असत्यापित	التاريخ غير مؤكد
remote	रिमोट	عن بُعد
hybrid	हाइब्रिड	هجين
onsite	ऑफ़िस से	من المكتب
full_time	फ़ुल-टाइम	دوام كامل
part_time	पार्ट-टाइम	دوام جزئي
internship	इंटर्नशिप	تدريب
contract	कॉन्ट्रैक्ट	عقد
freelance	फ़्रीलांस	عمل حر
temporary	अस्थायी	مؤقت
Target-role match	लक्षित भूमिका से मिलान	مطابقة الدور المستهدف
Skill match	कौशल मिलान	مطابقة المهارات
Location preference	स्थान पसंद	تفضيل الموقع
Remote available from your location	आपके स्थान से रिमोट उपलब्ध	متاح عن بُعد من موقعك
Compared with job description	जॉब विवरण से तुलना की गई	تمت المقارنة بالوصف الوظيفي
Experience fit	अनुभव के अनुरूप	مناسبة للخبرة
Experience requirement unverified	अनुभव की आवश्यकता असत्यापित	متطلب الخبرة غير مؤكد
Below your experience level	आपके अनुभव स्तर से नीचे	أقل من مستوى خبرتك
Posting date verified	पोस्टिंग की तारीख सत्यापित	تاريخ النشر مؤكد
Validated API source	सत्यापित API स्रोत	مصدر API موثّق
Description unavailable - confirm skills on posting	विवरण उपलब्ध नहीं - पोस्टिंग पर कौशल की पुष्टि करें	الوصف غير متاح - تأكد من المهارات في الإعلان
General profile relevance	सामान्य प्रोफ़ाइल प्रासंगिकता	ملاءمة عامة للملف
No job leads yet	अभी कोई जॉब लीड नहीं	لا توجد فرص عمل بعد
Run the agent with your resume and target roles to see matched postings here.	मेल खाती पोस्टिंग यहाँ देखने के लिए अपने रिज़्यूमे और लक्षित भूमिकाओं के साथ एजेंट चलाएँ।	شغّل الوكيل بسيرتك الذاتية والأدوار المستهدفة لترى الإعلانات المطابقة هنا.
No matching postings in this run	इस रन में कोई मेल खाती पोस्टिंग नहीं	لا إعلانات مطابقة في هذا التشغيل
Try a broader role or location, or search the portals below.	कोई व्यापक भूमिका या स्थान आज़माएँ, या नीचे दिए पोर्टल पर खोजें।	جرّب دورًا أو موقعًا أوسع، أو ابحث في البوابات أدناه.
Edit search	खोज बदलें	تعديل البحث
No leads match these filters	इन फ़िल्टर से कोई लीड मेल नहीं खाती	لا فرص تطابق هذه الفلاتر
Lower the minimum match or clear the search.	न्यूनतम मिलान कम करें या खोज साफ़ करें।	اخفض الحد الأدنى للتطابق أو امسح البحث.
Clear filters	फ़िल्टर साफ़ करें	مسح الفلاتر
Portal	पोर्टल	البوابة
Role & Location	भूमिका और स्थान	الدور والموقع
Match	मिलान	التطابق
Actions	कार्रवाइयाँ	الإجراءات
Loading jobs…	नौकरियाँ लोड हो रही हैं…	جارٍ تحميل الوظائف…
Unable to load more jobs.	और नौकरियाँ लोड नहीं हो सकीं।	تعذّر تحميل المزيد من الوظائف.
Unable to prepare resume.	रिज़्यूमे तैयार नहीं हो सका।	تعذّر إعداد السيرة الذاتية.
Unable to read resume status.	रिज़्यूमे की स्थिति पढ़ी नहीं जा सकी।	تعذّر قراءة حالة السيرة الذاتية.
Search more portals directly	सीधे और पोर्टल पर खोजें	ابحث مباشرة في بوابات أخرى
Indeed, Foundit and WorkIndia have no public job API, so these open the same search on their sites. With a Google for Jobs (JSearch) key their listings also appear above.	Indeed, Foundit और WorkIndia का कोई सार्वजनिक जॉब API नहीं है, इसलिए ये लिंक उनकी साइट पर वही खोज खोलते हैं। Google for Jobs (JSearch) कुंजी होने पर उनकी लिस्टिंग ऊपर भी दिखती हैं।	لا توفر Indeed وFoundit وWorkIndia واجهة API عامة للوظائف، لذا تفتح هذه الروابط البحث نفسه في مواقعها. ومع مفتاح Google for Jobs (JSearch) تظهر إعلاناتها أعلاه أيضًا.
How applicant tracking systems read your resume, what to fix first, and the validated ATS-ready resume to download.	एप्लिकेंट ट्रैकिंग सिस्टम आपका रिज़्यूमे कैसे पढ़ते हैं, पहले क्या सुधारें, और डाउनलोड के लिए सत्यापित ATS-तैयार रिज़्यूमे।	كيف تقرأ أنظمة تتبّع المتقدمين سيرتك الذاتية، وما يجب إصلاحه أولًا، والسيرة الجاهزة لـ ATS والموثّقة للتنزيل.
No ATS report yet	अभी कोई ATS रिपोर्ट नहीं	لا يوجد تقرير ATS بعد
Your score, the fixes that raise it and the ATS-ready resume downloads appear after your first run.	आपका स्कोर, उसे बढ़ाने वाले सुधार और ATS-तैयार रिज़्यूमे डाउनलोड आपके पहले रन के बाद दिखेंगे।	تظهر درجتك والتحسينات التي ترفعها وتنزيلات السيرة الجاهزة لـ ATS بعد أول تشغيل.
Confidence	विश्वास स्तर	الثقة
Estimated range	अनुमानित दायरा	النطاق التقديري
Text extraction	टेक्स्ट निष्कर्षण	استخراج النص
High	उच्च	مرتفعة
Moderate	मध्यम	متوسطة
Low	कम	منخفضة
not verified	सत्यापित नहीं	غير مؤكد
Resume improvements	रिज़्यूमे सुधार	تحسينات السيرة الذاتية
Score breakdown	स्कोर का विवरण	تفصيل الدرجة
No breakdown available.	कोई विवरण उपलब्ध नहीं।	لا يتوفر تفصيل.
Structure	संरचना	البنية
Skills & Keywords	कौशल और कीवर्ड	المهارات والكلمات المفتاحية
Experience & Projects	अनुभव और प्रोजेक्ट	الخبرة والمشاريع
Writing Quality	लेखन गुणवत्ता	جودة الكتابة
Missing keywords	छूटे हुए कीवर्ड	الكلمات المفتاحية الناقصة
No configured keywords are missing.	कोई कॉन्फ़िगर किया गया कीवर्ड नहीं छूटा है।	لا تنقص أي كلمات مفتاحية محددة.
Strengths	ताकतें	نقاط القوة
No major improvements found.	कोई बड़ा सुधार नहीं मिला।	لم يُعثر على تحسينات رئيسية.
Run with a job description for a sharper read.	और सटीक विश्लेषण के लिए जॉब विवरण के साथ चलाएँ।	شغّل مع وصف وظيفي لقراءة أدق.
ATS screening check against your job description	आपके जॉब विवरण के आधार पर ATS स्क्रीनिंग जाँच	فحص ATS مقابل الوصف الوظيفي
Job title appears in your resume	जॉब का पद आपके रिज़्यूमे में है	المسمى الوظيفي موجود في سيرتك
Job title partly matches	जॉब का पद आंशिक रूप से मेल खाता है	المسمى الوظيفي مطابق جزئيًا
Job title missing from your resume	जॉब का पद आपके रिज़्यूमे में नहीं है	المسمى الوظيفي غير موجود في سيرتك
Experience requirement met	अनुभव की आवश्यकता पूरी	متطلب الخبرة مستوفى
Experience slightly below the requirement	अनुभव आवश्यकता से थोड़ा कम	الخبرة أقل قليلًا من المطلوب
Experience below the requirement	अनुभव आवश्यकता से कम	الخبرة أقل من المطلوب
Experience	अनुभव	الخبرة
Risk:	जोखिम:	مخاطرة:
Run the agent to prepare a final ATS-friendly resume download.	अंतिम ATS-अनुकूल रिज़्यूमे डाउनलोड तैयार करने के लिए एजेंट चलाएँ।	شغّل الوكيل لإعداد سيرة نهائية متوافقة مع ATS للتنزيل.
Preparing the validated base resume…	सत्यापित मूल रिज़्यूमे तैयार हो रहा है…	جارٍ إعداد السيرة الأساسية الموثّقة…
Download ATS Resume DOCX	ATS रिज़्यूमे DOCX डाउनलोड करें	تنزيل سيرة ATS بصيغة DOCX
Download ATS Resume PDF	ATS रिज़्यूमे PDF डाउनलोड करें	تنزيل سيرة ATS بصيغة PDF
Each job lead also has its own tailored resume.	हर जॉब लीड का अपना अनुकूलित रिज़्यूमे भी है।	لكل فرصة عمل أيضًا سيرة ذاتية مخصصة.
Reusable Draft Message	दोबारा इस्तेमाल होने वाला ड्राफ़्ट संदेश	رسالة مسودة قابلة لإعادة الاستخدام
Reusable recruiter message	दोबारा इस्तेमाल होने वाला रिक्रूटर संदेश	رسالة قابلة لإعادة الاستخدام لمسؤولي التوظيف
Replace [Company Name] before applying to a selected job.	किसी चुनी गई जॉब पर आवेदन से पहले [Company Name] बदलें।	استبدل [Company Name] قبل التقديم على وظيفة مختارة.
Copy template	टेम्पलेट कॉपी करें	نسخ القالب
Template copied.	टेम्पलेट कॉपी हो गया।	تم نسخ القالب.
Press Ctrl+C (or Cmd+C) to copy the selected text.	चुना गया टेक्स्ट कॉपी करने के लिए Ctrl+C (या Cmd+C) दबाएँ।	اضغط Ctrl+C (أو Cmd+C) لنسخ النص المحدد.
No draft message was generated for this run.	इस रन के लिए कोई ड्राफ़्ट संदेश नहीं बना।	لم تُنشأ رسالة مسودة لهذا التشغيل.
No draft message was generated yet.	अभी कोई ड्राफ़्ट संदेश नहीं बना।	لم تُنشأ رسالة مسودة بعد.
No changes were recorded.	कोई बदलाव दर्ज नहीं हुआ।	لم تُسجَّل أي تغييرات.
What changed	क्या बदला	ما الذي تغيّر
Added skills and their evidence	जोड़े गए कौशल और उनके प्रमाण	المهارات المضافة وأدلتها
No employers, dates, degrees or metrics were changed.	कोई नियोक्ता, तारीख, डिग्री या आँकड़ा नहीं बदला गया।	لم يتغير أي صاحب عمل أو تاريخ أو شهادة أو رقم.
Download DOCX	DOCX डाउनलोड करें	تنزيل DOCX
Download PDF	PDF डाउनलोड करें	تنزيل PDF
Emails waiting for your approval	आपकी स्वीकृति की प्रतीक्षा में ईमेल	رسائل بانتظار موافقتك
Review the recipient and the exact text before anything is sent.	कुछ भी भेजने से पहले प्राप्तकर्ता और सटीक टेक्स्ट देखें।	راجع المستلم والنص بدقة قبل إرسال أي شيء.
No emails to review	समीक्षा के लिए कोई ईमेल नहीं	لا رسائل للمراجعة
Set Application mode to “Email recruiters after my approval” on Run & profile. Drafts appear here and nothing is sent until you approve.	रन और प्रोफ़ाइल में आवेदन मोड को “मेरी स्वीकृति के बाद रिक्रूटर को ईमेल करें” पर सेट करें। ड्राफ़्ट यहाँ दिखेंगे और आपकी स्वीकृति तक कुछ नहीं भेजा जाएगा।	اضبط وضع التقديم على «راسل مسؤولي التوظيف بعد موافقتي» في التشغيل والملف الشخصي. تظهر المسودات هنا ولا يُرسل شيء حتى توافق.
Open Run & profile	रन और प्रोफ़ाइल खोलें	فتح التشغيل والملف الشخصي
Subject	विषय	الموضوع
Message	संदेश	الرسالة
Approve and send	स्वीकृत करें और भेजें	وافق وأرسل
Confirm: send to this recruiter	पुष्टि करें: इस रिक्रूटर को भेजें	تأكيد: أرسل إلى مسؤول التوظيف هذا
Check the recipient and message, then confirm.	प्राप्तकर्ता और संदेश जाँचें, फिर पुष्टि करें।	تحقق من المستلم والرسالة ثم أكّد.
Reject	अस्वीकार करें	رفض
Waiting for approval	स्वीकृति की प्रतीक्षा	بانتظار الموافقة
Sending soon, undo available	जल्द भेजा जाएगा, पूर्ववत संभव	سيُرسل قريبًا، يمكن التراجع
Sending	भेजा जा रहा है	جارٍ الإرسال
Sent	भेजा गया	أُرسلت
Rejected	अस्वीकृत	مرفوضة
Failed	विफल	فشلت
Undone	पूर्ववत	تم التراجع
Approved. Sending after the undo window.	स्वीकृत। पूर्ववत करने का समय खत्म होने पर भेजा जाएगा।	تمت الموافقة. سيُرسل بعد انتهاء مهلة التراجع.
Rejected. This email will not be sent.	अस्वीकृत। यह ईमेल नहीं भेजा जाएगा।	مرفوضة. لن تُرسل هذه الرسالة.
Undone. The email is back in your queue.	पूर्ववत। ईमेल वापस आपकी कतार में है।	تم التراجع. عادت الرسالة إلى قائمتك.
Tailored resume	अनुकूलित रिज़्यूमे	سيرة ذاتية مخصصة
Your job search, run like a pipeline.	आपकी नौकरी की खोज, एक पाइपलाइन की तरह।	بحثك عن عمل، يُدار كخط إنتاج.
Sign in with an email OTP to access resume scoring, job discovery, recruiter draft templates, practice and daily run history.	रिज़्यूमे स्कोरिंग, नौकरी खोज, रिक्रूटर ड्राफ़्ट टेम्पलेट, अभ्यास और दैनिक रन इतिहास के लिए ईमेल OTP से साइन इन करें।	سجّل الدخول برمز OTP عبر البريد للوصول إلى تقييم السيرة واكتشاف الوظائف وقوالب الرسائل والتدريب وسجل التشغيل اليومي.
ATS score you can act on	ऐसा ATS स्कोर जिस पर आप काम कर सकें	درجة ATS يمكنك العمل عليها
See exactly which fixes raise it, then download a validated ATS-ready resume.	देखें कि कौन-से सुधार इसे बढ़ाते हैं, फिर सत्यापित ATS-तैयार रिज़्यूमे डाउनलोड करें।	اعرف بالضبط ما الذي يرفعها، ثم نزّل سيرة جاهزة لـ ATS وموثّقة.
Fresh, matched job leads	नई, मेल खाती जॉब लीड्स	فرص عمل جديدة ومطابقة
LinkedIn, Naukri and partner job boards, ranked against your skills and experience.	LinkedIn, Naukri और पार्टनर जॉब बोर्ड, आपके कौशल और अनुभव के आधार पर रैंक किए गए।	LinkedIn وNaukri ومواقع الوظائف الشريكة، مرتبة حسب مهاراتك وخبرتك.
Practice for the real job	असली नौकरी के लिए अभ्यास	تدرّب على الوظيفة الحقيقية
Job-specific mock tests, coding questions and interviews with daily and weekly reports.	जॉब के अनुसार मॉक टेस्ट, कोडिंग प्रश्न और इंटरव्यू, दैनिक और साप्ताहिक रिपोर्ट के साथ।	اختبارات تجريبية وأسئلة برمجة ومقابلات خاصة بالوظيفة مع تقارير يومية وأسبوعية.
Code	कोड	الرمز
Email OTP Sign In	ईमेल OTP से साइन इन	تسجيل الدخول برمز OTP
Enter your email and we will send a one-time sign-in code. No password needed.	अपना ईमेल दर्ज करें, हम एक बार इस्तेमाल होने वाला साइन-इन कोड भेजेंगे। पासवर्ड की ज़रूरत नहीं।	أدخل بريدك وسنرسل رمز دخول لمرة واحدة. لا حاجة لكلمة مرور.
Send OTP	OTP भेजें	إرسال الرمز
Send a new code	नया कोड भेजें	إرسال رمز جديد
6-digit code	6 अंकों का कोड	رمز من 6 أرقام
Verify and Continue	सत्यापित करें और जारी रखें	تحقق وتابع
Use a different email	दूसरा ईमेल इस्तेमाल करें	استخدم بريدًا آخر
New user? Verify your email first	नए उपयोगकर्ता? पहले अपना ईमेल सत्यापित करें	مستخدم جديد؟ تحقق من بريدك أولًا
Privacy notice	गोपनीयता सूचना	إشعار الخصوصية
Enter a valid email address like name@example.com.	name@example.com जैसा मान्य ईमेल पता दर्ज करें।	أدخل بريدًا إلكترونيًا صحيحًا مثل name@example.com.
Sending your code…	आपका कोड भेजा जा रहा है…	جارٍ إرسال الرمز…
Unable to send OTP.	OTP नहीं भेजा जा सका।	تعذّر إرسال الرمز.
Unable to reach the server. Check your connection and try again.	सर्वर से संपर्क नहीं हो सका। अपना कनेक्शन जाँचें और फिर कोशिश करें।	تعذّر الوصول إلى الخادم. تحقق من اتصالك وحاول مجددًا.
Unable to reach the server. Please try again.	सर्वर से संपर्क नहीं हो सका। कृपया फिर कोशिश करें।	تعذّر الوصول إلى الخادم. يرجى المحاولة مجددًا.
Verify your email	अपना ईमेल सत्यापित करें	تحقق من بريدك
Verify once, sign in with a code after.	एक बार सत्यापित करें, फिर कोड से साइन इन करें।	تحقق مرة واحدة، ثم سجّل الدخول برمز.
New users verify their email once through AWS SES. After verification, return to login and request your OTP normally.	नए उपयोगकर्ता AWS SES से एक बार अपना ईमेल सत्यापित करते हैं। सत्यापन के बाद लॉगिन पर लौटें और सामान्य रूप से OTP माँगें।	يتحقق المستخدمون الجدد من بريدهم مرة واحدة عبر AWS SES. بعد التحقق، عد إلى صفحة الدخول واطلب الرمز كالمعتاد.
New User Registration	नए उपयोगकर्ता का पंजीकरण	تسجيل مستخدم جديد
Enter your email address. AWS will send a verification email with a link that approves this address for sign-in codes.	अपना ईमेल पता दर्ज करें। AWS एक सत्यापन ईमेल भेजेगा जिसके लिंक से यह पता साइन-इन कोड के लिए स्वीकृत हो जाएगा।	أدخل بريدك الإلكتروني. سترسل AWS رسالة تحقق برابط يعتمد هذا العنوان لرموز الدخول.
Send Verification Link	सत्यापन लिंक भेजें	إرسال رابط التحقق
Requesting the AWS verification email…	AWS सत्यापन ईमेल का अनुरोध किया जा रहा है…	جارٍ طلب رسالة التحقق من AWS…
Unable to request verification right now.	अभी सत्यापन का अनुरोध नहीं हो सका।	تعذّر طلب التحقق الآن.
Verification email requested. Check your inbox.	सत्यापन ईमेल का अनुरोध हो गया। अपना इनबॉक्स देखें।	تم طلب رسالة التحقق. تفقد بريدك الوارد.
After clicking the AWS verification link, come back to the login page and click Send OTP.	AWS सत्यापन लिंक पर क्लिक करने के बाद लॉगिन पेज पर लौटें और OTP भेजें पर क्लिक करें।	بعد النقر على رابط التحقق من AWS، عد إلى صفحة الدخول وانقر إرسال الرمز.
Back to Login	लॉगिन पर वापस जाएँ	العودة إلى تسجيل الدخول
Daily and weekly trends for your mock tests and mock interviews, for all practice or one job.	आपके मॉक टेस्ट और मॉक इंटरव्यू के दैनिक और साप्ताहिक रुझान, सारे अभ्यास या एक जॉब के लिए।	الاتجاهات اليومية والأسبوعية لاختباراتك ومقابلاتك التجريبية، لكل التدريب أو لوظيفة واحدة.
Period	अवधि	الفترة
Daily (14 days)	दैनिक (14 दिन)	يومي (14 يومًا)
Weekly (8 weeks)	साप्ताहिक (8 सप्ताह)	أسبوعي (8 أسابيع)
Job	जॉब	الوظيفة
All practice	सारा अभ्यास	كل التدريب
Summary	सारांश	الملخص
What to do next	आगे क्या करें	ما الذي تفعله بعد ذلك
Mock Test scores	मॉक टेस्ट स्कोर	درجات الاختبار التجريبي
Attempts	प्रयास	المحاولات
Average score %	औसत स्कोर %	متوسط الدرجة %
Mock Interview scores	मॉक इंटरव्यू स्कोर	درجات المقابلة التجريبية
Sessions	सत्र	الجلسات
Average score	औसत स्कोर	متوسط الدرجة
Topic accuracy (Mock Test)	विषय सटीकता (मॉक टेस्ट)	دقة المواضيع (الاختبار التجريبي)
Interview skills	इंटरव्यू कौशल	مهارات المقابلة
By difficulty and coding	कठिनाई और कोडिंग के अनुसार	حسب الصعوبة والبرمجة
Interview question types	इंटरव्यू प्रश्नों के प्रकार	أنواع أسئلة المقابلة
Recent tests	हाल के टेस्ट	الاختبارات الأخيرة
Recent interviews	हाल के इंटरव्यू	المقابلات الأخيرة
Readiness index	तैयारी सूचकांक	مؤشر الجاهزية
Practice streak	अभ्यास की लगातार अवधि	سلسلة التدريب
Mock Test average	मॉक टेस्ट औसत	متوسط الاختبار التجريبي
Interview average	इंटरव्यू औसत	متوسط المقابلة
Completed	पूरे हुए	المكتملة
No earlier data to compare	तुलना के लिए पहले का डेटा नहीं	لا بيانات سابقة للمقارنة
No data yet.	अभी कोई डेटा नहीं।	لا بيانات بعد.
Score trend	स्कोर का रुझान	اتجاه الدرجة
Practise to see your readiness	अपनी तैयारी देखने के लिए अभ्यास करें	تدرّب لترى جاهزيتك
Interview ready	इंटरव्यू के लिए तैयार	جاهز للمقابلة
Getting there	लगभग पहुँच रहे हैं	تقترب من الهدف
Needs focused practice	केंद्रित अभ्यास की ज़रूरत	يحتاج إلى تدريب مركّز
Topic	विषय	الموضوع
Accuracy	सटीकता	الدقة
Code questions	कोड प्रश्न	أسئلة البرمجة
Complete a mock test to see topic accuracy.	विषय सटीकता देखने के लिए एक मॉक टेस्ट पूरा करें।	أكمل اختبارًا تجريبيًا لترى دقة المواضيع.
Complete a mock interview to see skill scores.	कौशल स्कोर देखने के लिए एक मॉक इंटरव्यू पूरा करें।	أكمل مقابلة تجريبية لترى درجات المهارات.
No graded questions yet.	अभी कोई ग्रेड किए गए प्रश्न नहीं।	لا أسئلة مصححة بعد.
No interview answers yet.	अभी कोई इंटरव्यू उत्तर नहीं।	لا إجابات مقابلة بعد.
No tests in this window.	इस अवधि में कोई टेस्ट नहीं।	لا اختبارات في هذه الفترة.
Start a mock test	मॉक टेस्ट शुरू करें	ابدأ اختبارًا تجريبيًا
No interviews in this window.	इस अवधि में कोई इंटरव्यू नहीं।	لا مقابلات في هذه الفترة.
Start a mock interview	मॉक इंटरव्यू शुरू करें	ابدأ مقابلة تجريبية
Score	स्कोर	الدرجة
Date	तारीख	التاريخ
Interview	इंटरव्यू	المقابلة
General practice	सामान्य अभ्यास	تدريب عام
Communication	संवाद	التواصل
Technical accuracy	तकनीकी सटीकता	الدقة التقنية
Confidence	विश्वास स्तर	الثقة
Problem solving	समस्या समाधान	حل المشكلات
easy	आसान	سهل
medium	मध्यम	متوسط
hard	कठिन	صعب
mixed	मिश्रित	مختلط
quick	त्वरित	سريع
standard	मानक	قياسي
full	पूर्ण	كامل
How we use your data	हम आपके डेटा का उपयोग कैसे करते हैं	كيف نستخدم بياناتك
We use your resume and profile only to score ATS readiness, find matching jobs, prepare tailored resumes and application drafts, and run practice tests and interviews for you. Recruiter emails are sent only after you approve each one. You can download or delete your data at any time.	हम आपके रिज़्यूमे और प्रोफ़ाइल का उपयोग केवल ATS तैयारी स्कोर करने, मेल खाती नौकरियाँ ढूँढने, अनुकूलित रिज़्यूमे और आवेदन ड्राफ़्ट तैयार करने, और आपके लिए अभ्यास टेस्ट व इंटरव्यू चलाने के लिए करते हैं। रिक्रूटर ईमेल हर एक की आपकी स्वीकृति के बाद ही भेजे जाते हैं। आप कभी भी अपना डेटा डाउनलोड या डिलीट कर सकते हैं।	نستخدم سيرتك الذاتية وملفك فقط لتقييم الجاهزية لـ ATS، والعثور على الوظائف المطابقة، وإعداد السير المخصصة ومسودات التقديم، وإجراء الاختبارات والمقابلات التدريبية لك. لا تُرسل رسائل مسؤولي التوظيف إلا بعد موافقتك على كل واحدة. ويمكنك تنزيل بياناتك أو حذفها في أي وقت.
What we store:	हम क्या संग्रहित करते हैं:	ما نخزّنه:
your resume file and text, profile (roles, skills, locations, links), job leads found for you, tailored resumes, mock test and interview answers and scores, and approval decisions.	आपकी रिज़्यूमे फ़ाइल और टेक्स्ट, प्रोफ़ाइल (भूमिकाएँ, कौशल, स्थान, लिंक), आपके लिए मिली जॉब लीड्स, अनुकूलित रिज़्यूमे, मॉक टेस्ट और इंटरव्यू के उत्तर और स्कोर, और स्वीकृति के निर्णय।	ملف سيرتك ونصها، والملف الشخصي (الأدوار والمهارات والمواقع والروابط)، وفرص العمل التي وُجدت لك، والسير المخصصة، وإجابات الاختبارات والمقابلات ودرجاتها، وقرارات الموافقة.
What we never use:	हम क्या कभी उपयोग नहीं करते:	ما لا نستخدمه أبدًا:
age, gender, religion, caste, marital status, photo or other personal attributes are not used for matching or scoring, and are removed before any AI review.	उम्र, लिंग, धर्म, जाति, वैवाहिक स्थिति, फ़ोटो या अन्य निजी विशेषताएँ मिलान या स्कोरिंग में उपयोग नहीं होतीं, और किसी भी AI समीक्षा से पहले हटा दी जाती हैं।	لا يُستخدم العمر أو الجنس أو الدين أو الطائفة أو الحالة الاجتماعية أو الصورة أو أي سمات شخصية أخرى في المطابقة أو التقييم، وتُحذف قبل أي مراجعة بالذكاء الاصطناعي.
AI services:	AI सेवाएँ:	خدمات الذكاء الاصطناعي:
when enabled, parts of your resume or answers are sent to an AI provider for feedback, without storing them at the provider.	चालू होने पर, फ़ीडबैक के लिए आपके रिज़्यूमे या उत्तरों के हिस्से AI प्रदाता को भेजे जाते हैं, प्रदाता के पास संग्रहित किए बिना।	عند التفعيل، تُرسل أجزاء من سيرتك أو إجاباتك إلى مزوّد ذكاء اصطناعي للحصول على ملاحظات، دون تخزينها لدى المزوّد.
Retention:	संग्रहण अवधि:	الاحتفاظ:
Your rights:	आपके अधिकार:	حقوقك:
download or delete your data below at any time, or withdraw consent by deleting your account.	नीचे कभी भी अपना डेटा डाउनलोड या डिलीट करें, या अपना खाता डिलीट करके सहमति वापस लें।	نزّل بياناتك أو احذفها أدناه في أي وقت، أو اسحب موافقتك بحذف حسابك.
Your consent	आपकी सहमति	موافقتك
Accept the notice	सूचना स्वीकार करें	قبول الإشعار
Notice accepted.	सूचना स्वीकार की गई।	تم قبول الإشعار.
Download my data	मेरा डेटा डाउनलोड करें	تنزيل بياناتي
A JSON file with your profile, runs, job leads, tests, interviews, approval queue and activity log.	आपकी प्रोफ़ाइल, रन, जॉब लीड्स, टेस्ट, इंटरव्यू, स्वीकृति कतार और गतिविधि लॉग वाली एक JSON फ़ाइल।	ملف JSON يتضمن ملفك وعمليات التشغيل وفرص العمل والاختبارات والمقابلات وقائمة الموافقات وسجل النشاط.
Delete my account	मेरा खाता डिलीट करें	حذف حسابي
Permanently removes your resume, profile, runs, tailored resumes, tests, interviews, drafts and schedule. This cannot be undone.	आपका रिज़्यूमे, प्रोफ़ाइल, रन, अनुकूलित रिज़्यूमे, टेस्ट, इंटरव्यू, ड्राफ़्ट और शेड्यूल हमेशा के लिए हटा देता है। इसे पूर्ववत नहीं किया जा सकता।	يحذف نهائيًا سيرتك وملفك وعمليات التشغيل والسير المخصصة والاختبارات والمقابلات والمسودات والجدول. لا يمكن التراجع عن ذلك.
Type your email to confirm	पुष्टि के लिए अपना ईमेल लिखें	اكتب بريدك للتأكيد
Delete everything	सब कुछ डिलीट करें	حذف كل شيء
Deleting…	डिलीट हो रहा है…	جارٍ الحذف…
Your account and data were deleted. Redirecting…	आपका खाता और डेटा डिलीट हो गया। आगे भेजा जा रहा है…	تم حذف حسابك وبياناتك. جارٍ التحويل…
Activity log	गतिविधि लॉग	سجل النشاط
Consents, approvals, sent emails and data exports for your account.	आपके खाते की सहमतियाँ, स्वीकृतियाँ, भेजे गए ईमेल और डेटा एक्सपोर्ट।	الموافقات والاعتمادات والرسائل المرسلة وعمليات تصدير البيانات لحسابك.
No recorded actions yet.	अभी कोई दर्ज कार्रवाई नहीं।	لا إجراءات مسجلة بعد.
When	कब	متى
Action	कार्रवाई	الإجراء
Details	विवरण	التفاصيل
consent given	सहमति दी गई	تم منح الموافقة
approval queued	स्वीकृति के लिए कतार में	أُضيفت إلى قائمة الموافقة
approval approved	स्वीकृत	تمت الموافقة
approval undone	स्वीकृति पूर्ववत	تم التراجع عن الموافقة
approval rejected	अस्वीकृत	مرفوضة
approval sent	ईमेल भेजा गया	أُرسلت الرسالة
approval send failed	ईमेल भेजना विफल	فشل إرسال الرسالة
data exported	डेटा एक्सपोर्ट किया गया	تم تصدير البيانات
Window	अवधि	الفترة
Last 24 hours	पिछले 24 घंटे	آخر 24 ساعة
Last 7 days	पिछले 7 दिन	آخر 7 أيام
Last 30 days	पिछले 30 दिन	آخر 30 يومًا
Refresh	रीफ़्रेश करें	تحديث
Quality, coverage, human-in-the-loop, practice, operations, AI cost and business metrics. CloudWatch receives the same events as Embedded Metric Format logs.	गुणवत्ता, कवरेज, मानवीय निगरानी, अभ्यास, संचालन, AI लागत और व्यावसायिक मेट्रिक्स। CloudWatch को यही इवेंट Embedded Metric Format लॉग के रूप में मिलते हैं।	مقاييس الجودة والتغطية والإشراف البشري والتدريب والتشغيل وتكلفة الذكاء الاصطناعي والأعمال. يتلقى CloudWatch الأحداث نفسها كسجلات Embedded Metric Format.
Recommendation quality	सुझाव की गुणवत्ता	جودة التوصيات
Coverage	कवरेज	التغطية
Human in the loop	मानवीय निगरानी	الإشراف البشري
Mock tests and interviews	मॉक टेस्ट और इंटरव्यू	الاختبارات والمقابلات التجريبية
Operations	संचालन	التشغيل
AI usage and cost	AI उपयोग और लागत	استخدام الذكاء الاصطناعي وتكلفته
Business	व्यवसाय	الأعمال
No alerts in this window.	इस अवधि में कोई अलर्ट नहीं।	لا تنبيهات في هذه الفترة.
High:	उच्च:	مرتفع:
Medium:	मध्यम:	متوسط:
Mock Test · Job-Specific Assessment	मॉक टेस्ट · जॉब-विशेष मूल्यांकन	اختبار تجريبي · تقييم خاص بالوظيفة
Multiple-choice questions tailored to your job leads	आपकी जॉब लीड्स के अनुसार बहुविकल्पीय प्रश्न	أسئلة اختيار من متعدد مخصصة لفرص عملك
Set up your test	अपना टेस्ट सेट करें	أعدّ اختبارك
Pick a job lead and the test is built from its required skills, the skills you matched, and its Additional Skills, plus aptitude and reasoning questions used in screening rounds.	एक जॉब लीड चुनें; टेस्ट उसके ज़रूरी कौशल, आपके मेल खाते कौशल और उसके अतिरिक्त कौशल से बनता है, साथ में स्क्रीनिंग राउंड वाले एप्टीट्यूड और रीज़निंग प्रश्न भी।	اختر فرصة عمل ويُبنى الاختبار من مهاراتها المطلوبة والمهارات التي تطابقها ومهاراتها الإضافية، مع أسئلة قدرات واستدلال تُستخدم في جولات الفرز.
Job lead	जॉब लीड	فرصة العمل
Loading your job leads…	आपकी जॉब लीड्स लोड हो रही हैं…	جارٍ تحميل فرص عملك…
Test length	टेस्ट की लंबाई	طول الاختبار
Quick	त्वरित	سريع
Standard	मानक	قياسي
Full	पूर्ण	كامل
10 questions · ~13 min	10 प्रश्न · ~13 मिनट	10 أسئلة · ~13 دقيقة
20 questions · ~25 min	20 प्रश्न · ~25 मिनट	20 سؤالًا · ~25 دقيقة
30 questions · ~38 min	30 प्रश्न · ~38 मिनट	30 سؤالًا · ~38 دقيقة
Difficulty	कठिनाई	الصعوبة
Mixed - matched to your experience (recommended)	मिश्रित - आपके अनुभव के अनुसार (सुझाया गया)	مختلط - حسب خبرتك (موصى به)
Mostly easy	ज़्यादातर आसान	سهل في الغالب
Mostly medium	ज़्यादातर मध्यम	متوسط في الغالب
Mostly hard	ज़्यादातर कठिन	صعب في الغالب
Start Mock Test	मॉक टेस्ट शुरू करें	ابدأ الاختبار التجريبي
How it works	यह कैसे काम करता है	كيف يعمل
One correct answer per question; no negative marking.	हर प्रश्न का एक सही उत्तर; कोई नेगेटिव मार्किंग नहीं।	إجابة صحيحة واحدة لكل سؤال؛ بلا خصم للدرجات.
The timer runs on the server. The test auto-submits when time is up.	टाइमर सर्वर पर चलता है। समय खत्म होने पर टेस्ट अपने-आप सबमिट हो जाता है।	يعمل المؤقت على الخادم. يُسلَّم الاختبار تلقائيًا عند انتهاء الوقت.
Move between questions freely and mark any for review.	प्रश्नों के बीच आराम से जाएँ और किसी को भी समीक्षा के लिए चिह्नित करें।	تنقّل بين الأسئلة بحرية وعلّم أيًا منها للمراجعة.
Your answers are saved in this browser if the page reloads.	पेज दोबारा लोड होने पर भी आपके उत्तर इस ब्राउज़र में सेव रहते हैं।	تُحفظ إجاباتك في هذا المتصفح إذا أُعيد تحميل الصفحة.
Answers and explanations are shown only after you submit.	उत्तर और व्याख्या सबमिट करने के बाद ही दिखते हैं।	تظهر الإجابات والشروح بعد التسليم فقط.
Each retake prefers questions you have not seen before.	हर बार दोबारा देने पर नए प्रश्नों को प्राथमिकता मिलती है।	تفضّل كل إعادة الأسئلة التي لم ترها من قبل.
Technical jobs include code questions: predict the output, spot the bug, estimate complexity. Every code answer is verified by running it.	तकनीकी जॉब में कोड प्रश्न होते हैं: आउटपुट बताएँ, बग पकड़ें, जटिलता का अनुमान लगाएँ। हर कोड उत्तर को चलाकर सत्यापित किया गया है।	تتضمن الوظائف التقنية أسئلة برمجة: توقّع الناتج، اكتشف الخطأ، قدّر التعقيد. كل إجابة برمجية موثّقة بتشغيلها.
The difficulty mix you choose is applied exactly; your daily and weekly trends are in	आपका चुना कठिनाई मिश्रण ठीक वैसा ही लागू होता है; आपके दैनिक और साप्ताहिक रुझान यहाँ हैं:	يُطبَّق مزيج الصعوبة الذي تختاره بدقة؛ واتجاهاتك اليومية والأسبوعية في
No completed tests yet.	अभी कोई टेस्ट पूरा नहीं हुआ।	لا اختبارات مكتملة بعد.
Recent tests	हाल के टेस्ट	الاختبارات الأخيرة
Result	परिणाम	النتيجة
History is unavailable right now.	इतिहास अभी उपलब्ध नहीं है।	السجل غير متاح الآن.
Building your test…	आपका टेस्ट बन रहा है…	جارٍ إنشاء اختبارك…
Code for this question	इस प्रश्न का कोड	رمز هذا السؤال
← Previous	← पिछला	السابق →
Next →	अगला →	← التالي
Mark for review	समीक्षा के लिए चिह्नित करें	علّم للمراجعة
Unmark review	समीक्षा चिह्न हटाएँ	إلغاء علامة المراجعة
Clear answer	उत्तर साफ़ करें	مسح الإجابة
Questions	प्रश्न	الأسئلة
Answered	उत्तर दिए	تمت الإجابة
Not answered	उत्तर नहीं दिए	لم تتم الإجابة
Marked	चिह्नित	مُعلَّمة
Marked for review	समीक्षा के लिए चिह्नित	مُعلَّمة للمراجعة
Submit Test	टेस्ट सबमिट करें	تسليم الاختبار
Submitting…	सबमिट हो रहा है…	جارٍ التسليم…
Review & submit	देखें और सबमिट करें	راجع وسلّم
Time left	बचा समय	الوقت المتبقي
Time is up — submitting…	समय खत्म — सबमिट हो रहा है…	انتهى الوقت — جارٍ التسليم…
Shortcuts: 1–4 or A–D to answer · ← → to move · M to mark	शॉर्टकट: उत्तर के लिए 1–4 या A–D · आगे-पीछे के लिए ← → · चिह्नित करने के लिए M	الاختصارات: 1–4 أو A–D للإجابة · ← → للتنقل · M للتعليم
Scorecard	स्कोरकार्ड	بطاقة النتائج
Topic breakdown	विषयवार विवरण	تفصيل المواضيع
Difficulty breakdown	कठिनाईवार विवरण	تفصيل الصعوبة
Focus next	अगला फ़ोकस	ركّز بعد ذلك
Answer review	उत्तरों की समीक्षा	مراجعة الإجابات
All	सभी	الكل
Incorrect	गलत	خاطئة
Unanswered	बिना उत्तर	بلا إجابة
Correct	सही	صحيحة
Retake with new questions	नए प्रश्नों के साथ दोबारा दें	أعد الاختبار بأسئلة جديدة
Choose another job	दूसरी जॉब चुनें	اختر وظيفة أخرى
Practise the interview	इंटरव्यू का अभ्यास करें	تدرّب على المقابلة
Back to Dashboard	डैशबोर्ड पर वापस जाएँ	العودة إلى لوحة التحكم
Excellent	उत्कृष्ट	ممتاز
Good	अच्छा	جيد
Average	औसत	متوسط
Needs improvement	सुधार की ज़रूरत	يحتاج إلى تحسين
Ready to apply	आवेदन के लिए तैयार	جاهز للتقديم
Almost ready	लगभग तैयार	جاهز تقريبًا
Prepare before applying	आवेदन से पहले तैयारी करें	استعد قبل التقديم
Time used	लगा समय	الوقت المستغرق
No topic below 50%. Keep practising the lowest bars above.	कोई विषय 50% से नीचे नहीं। ऊपर के सबसे छोटे बार वाले विषयों का अभ्यास जारी रखें।	لا موضوع أقل من 50%. واصل التدرب على أقصر الأشرطة أعلاه.
This attempt was submitted after the time limit. Practise pacing: about one minute per question.	यह प्रयास समय सीमा के बाद सबमिट हुआ। गति का अभ्यास करें: हर प्रश्न पर लगभग एक मिनट।	سُلّمت هذه المحاولة بعد انتهاء الوقت. تدرّب على الإيقاع: نحو دقيقة لكل سؤال.
Report a problem with this question	इस प्रश्न में समस्या बताएँ	أبلغ عن مشكلة في هذا السؤال
Reported - thank you. A reviewer will check this question.	रिपोर्ट हो गया - धन्यवाद। एक समीक्षक इस प्रश्न की जाँच करेगा।	تم الإبلاغ - شكرًا. سيراجع أحد المراجعين هذا السؤال.
Please sign in again.	कृपया फिर से साइन इन करें।	يرجى تسجيل الدخول مجددًا.
General practice (from your profile)	सामान्य अभ्यास (आपकी प्रोफ़ाइल से)	تدريب عام (من ملفك)
Run the agent from the dashboard to get job-specific tests.	जॉब-विशेष टेस्ट के लिए डैशबोर्ड से एजेंट चलाएँ।	شغّل الوكيل من لوحة التحكم للحصول على اختبارات خاصة بالوظيفة.
Topics are chosen from the job title and description.	विषय जॉब के पद और विवरण से चुने जाते हैं।	تُختار المواضيع من المسمى والوصف الوظيفي.
Mock Interview Agent · Virtual Interview Studio	मॉक इंटरव्यू एजेंट · वर्चुअल इंटरव्यू स्टूडियो	وكيل المقابلة التجريبية · استوديو المقابلات الافتراضي
Elapsed	बीता समय	المنقضي
Progress	प्रगति	التقدم
Voice	आवाज़	الصوت
Interview Setup	इंटरव्यू सेटअप	إعداد المقابلة
Pick a job lead to practise for that exact role, then choose accent, length, and camera.	उसी भूमिका के अभ्यास के लिए एक जॉब लीड चुनें, फिर लहजा, लंबाई और कैमरा चुनें।	اختر فرصة عمل للتدرب على ذلك الدور تحديدًا، ثم اختر اللهجة والطول والكاميرا.
General practice (profile roles)	सामान्य अभ्यास (प्रोफ़ाइल की भूमिकाएँ)	تدريب عام (أدوار الملف)
Interviewer accent	इंटरव्यूअर का लहजा	لهجة المحاور
Indian English	भारतीय अंग्रेज़ी	الإنجليزية الهندية
American English	अमेरिकी अंग्रेज़ी	الإنجليزية الأمريكية
British English	ब्रिटिश अंग्रेज़ी	الإنجليزية البريطانية
Australian English	ऑस्ट्रेलियाई अंग्रेज़ी	الإنجليزية الأسترالية
Canadian English	कनाडाई अंग्रेज़ी	الإنجليزية الكندية
Singapore English	सिंगापुरी अंग्रेज़ी	الإنجليزية السنغافورية
Preview voice	आवाज़ सुनें	معاينة الصوت
Checking regional voices...	क्षेत्रीय आवाज़ें जाँची जा रही हैं...	جارٍ فحص الأصوات الإقليمية...
Interview length	इंटरव्यू की लंबाई	طول المقابلة
Standard - 8 balanced questions	मानक - 8 संतुलित प्रश्न	قياسي - 8 أسئلة متوازنة
Quick confidence round - 5 foundation questions	त्वरित आत्मविश्वास राउंड - 5 बुनियादी प्रश्न	جولة ثقة سريعة - 5 أسئلة أساسية
Deep practice - 10 advanced questions	गहन अभ्यास - 10 उन्नत प्रश्न	تدريب معمّق - 10 أسئلة متقدمة
Enable Camera	कैमरा चालू करें	تشغيل الكاميرا
Turn Camera Off	कैमरा बंद करें	إيقاف الكاميرا
Start Interview	इंटरव्यू शुरू करें	ابدأ المقابلة
End	समाप्त करें	إنهاء
Current Question	मौजूदा प्रश्न	السؤال الحالي
Ready	तैयार	جاهز
Start the interview to receive the first role-specific question.	भूमिका-विशेष पहला प्रश्न पाने के लिए इंटरव्यू शुरू करें।	ابدأ المقابلة لتتلقى أول سؤال خاص بالدور.
Tip: answer with situation, technical action, tradeoff, and measurable result.	सुझाव: स्थिति, तकनीकी कदम, ट्रेड-ऑफ़ और मापने योग्य परिणाम के साथ उत्तर दें।	نصيحة: أجب بالموقف والإجراء التقني والموازنة والنتيجة القابلة للقياس.
AI interviewer avatar	AI इंटरव्यूअर अवतार	صورة المحاور الآلي
AI Interviewer - Sarah	AI इंटरव्यूअर - सारा	المحاورة الآلية - سارة
Ready to begin a professional mock interview.	एक प्रोफ़ेशनल मॉक इंटरव्यू शुरू करने के लिए तैयार।	جاهزة لبدء مقابلة تجريبية احترافية.
Replay	फिर से सुनें	إعادة التشغيل
Record	रिकॉर्ड करें	تسجيل
Stop	रोकें	إيقاف
Camera preview appears here after permission is granted.	अनुमति मिलने के बाद कैमरा प्रीव्यू यहाँ दिखेगा।	تظهر معاينة الكاميرا هنا بعد منح الإذن.
Camera preview is not available in this browser. Interview can continue without video.	इस ब्राउज़र में कैमरा प्रीव्यू उपलब्ध नहीं है। इंटरव्यू बिना वीडियो के जारी रह सकता है।	معاينة الكاميرا غير متاحة في هذا المتصفح. يمكن متابعة المقابلة بدون فيديو.
Camera permission was not granted. Interview can continue without video.	कैमरा की अनुमति नहीं मिली। इंटरव्यू बिना वीडियो के जारी रह सकता है।	لم يُمنح إذن الكاميرا. يمكن متابعة المقابلة بدون فيديو.
Your video	आपका वीडियो	الفيديو الخاص بك
Your Answer	आपका उत्तर	إجابتك
Code Answer	कोड उत्तर	إجابة برمجية
Idle	निष्क्रिय	خامل
Editor	एडिटर	المحرر
Response transcript	उत्तर का ट्रांसक्रिप्ट	نص الإجابة
Speak after clicking Record, or type your answer here. Use examples, technical depth, and measurable impact.	रिकॉर्ड पर क्लिक करके बोलें, या अपना उत्तर यहाँ लिखें। उदाहरण, तकनीकी गहराई और मापने योग्य प्रभाव बताएँ।	تحدث بعد النقر على تسجيل، أو اكتب إجابتك هنا. استخدم أمثلة وعمقًا تقنيًا وأثرًا قابلًا للقياس.
Code response	कोड उत्तर	إجابة برمجية
Coding problems: press Run sample tests to check your code. It runs only in your browser, never on our server.	कोडिंग समस्याएँ: अपना कोड जाँचने के लिए सैंपल टेस्ट चलाएँ दबाएँ। यह केवल आपके ब्राउज़र में चलता है, हमारे सर्वर पर कभी नहीं।	مسائل البرمجة: اضغط تشغيل الاختبارات النموذجية لفحص الرمز. يعمل في متصفحك فقط، ولا يعمل على خادمنا أبدًا.
Other / Plain text	अन्य / सादा टेक्स्ट	أخرى / نص عادي
Code response editor	कोड उत्तर एडिटर	محرر الإجابة البرمجية
Write your solution here...	अपना समाधान यहाँ लिखें...	اكتب حلك هنا...
Submit & Next	सबमिट करें और आगे बढ़ें	سلّم وانتقل للتالي
Clear	साफ़ करें	مسح
Interview Transcript	इंटरव्यू ट्रांसक्रिप्ट	نص المقابلة
Resume templates	रिज़्यूमे टेम्पलेट	قوالب السيرة الذاتية
Every template is a single text column with standard headings and no tables, icons or photos, so applicant tracking systems read it correctly. Each one is checked after it is built.	हर टेम्पलेट एक ही कॉलम का टेक्स्ट है, जिसमें मानक शीर्षक हैं और कोई तालिका, आइकन या फ़ोटो नहीं, ताकि एप्लिकेंट ट्रैकिंग सिस्टम उसे सही पढ़ सकें। बनने के बाद हर एक की जाँच की जाती है।	كل قالب عمود نصي واحد بعناوين قياسية وبلا جداول أو أيقونات أو صور، لتقرأه أنظمة تتبّع المتقدمين بشكل صحيح. ويُفحص كل قالب بعد إنشائه.
Recommended	सुझाया गया	موصى به
Your main resume	आपका मुख्य रिज़्यूमे	سيرتك الرئيسية
ATS check passed	ATS जाँच पास	اجتاز فحص ATS
Used for tailored resumes	अनुकूलित रिज़्यूमे के लिए उपयोग	مستخدم للسير المخصصة
Use for tailored resumes	अनुकूलित रिज़्यूमे के लिए उपयोग करें	استخدمه للسير المخصصة
Build in this template	इस टेम्पलेट में बनाएँ	أنشئ بهذا القالب
Building this template…	यह टेम्पलेट बन रहा है…	جارٍ إنشاء هذا القالب…
Retry this template	यह टेम्पलेट फिर से आज़माएँ	أعد محاولة هذا القالب
Resume template	रिज़्यूमे टेम्पलेट	قالب السيرة الذاتية
Page 1 of your resume in this template	इस टेम्पलेट में आपके रिज़्यूमे का पहला पेज	الصفحة الأولى من سيرتك بهذا القالب
Prepare this template first.	पहले यह टेम्पलेट तैयार करें।	أعدّ هذا القالب أولًا.
Unknown resume template.	अज्ञात रिज़्यूमे टेम्पलेट।	قالب سيرة ذاتية غير معروف.
Preview is not available.	प्रीव्यू उपलब्ध नहीं है।	المعاينة غير متاحة.
Classic Professional	क्लासिक प्रोफ़ेशनल	احترافي كلاسيكي
Modern Clean	मॉडर्न क्लीन	حديث وبسيط
Technical	टेक्निकल	تقني
Fresher / Graduate	फ्रेशर / ग्रेजुएट	حديث التخرج
Executive	एग्ज़ीक्यूटिव	تنفيذي
Most roles and industries	ज़्यादातर भूमिकाएँ और उद्योग	معظم الأدوار والقطاعات
Product, design, marketing and business roles	प्रोडक्ट, डिज़ाइन, मार्केटिंग और बिज़नेस भूमिकाएँ	أدوار المنتج والتصميم والتسويق والأعمال
Software, data, AI, cloud and engineering roles	सॉफ़्टवेयर, डेटा, AI, क्लाउड और इंजीनियरिंग भूमिकाएँ	أدوار البرمجيات والبيانات والذكاء الاصطناعي والسحابة والهندسة
Students, freshers and up to 2 years of experience	छात्र, फ्रेशर और 2 वर्ष तक का अनुभव	الطلاب وحديثو التخرج وحتى سنتين من الخبرة
Senior, lead and management roles (8+ years)	वरिष्ठ, लीड और प्रबंधन भूमिकाएँ (8+ वर्ष)	الأدوار العليا والقيادية والإدارية (8+ سنوات)
Centred name, navy section headings with a thin rule. The safest choice for any ATS.	बीच में नाम, पतली रेखा के साथ नेवी रंग के शीर्षक। किसी भी ATS के लिए सबसे सुरक्षित विकल्प।	اسم في المنتصف وعناوين أقسام كحلية بخط رفيع. الخيار الأكثر أمانًا لأي نظام ATS.
Left-aligned name with a teal accent line and title-case headings. Contemporary but plain text.	बाईं ओर नाम, टील रंग की रेखा और सामान्य केस में शीर्षक। आधुनिक, फिर भी सादा टेक्स्ट।	اسم محاذٍ لليسار مع خط بلون أزرق مخضر وعناوين بأحرف استهلالية. عصري لكنه نص عادي.
Skills and projects first, compact spacing, dark slate accents. Puts your stack where recruiters look.	पहले कौशल और प्रोजेक्ट, कसी हुई जगह, गहरे स्लेटी रंग। आपकी तकनीकें वहीं जहाँ रिक्रूटर देखते हैं।	المهارات والمشاريع أولًا، بتباعد مضغوط ولمسات رمادية داكنة. يضع تقنياتك حيث ينظر مسؤولو التوظيف.
Education, skills and projects before experience, so your strongest evidence comes first.	अनुभव से पहले शिक्षा, कौशल और प्रोजेक्ट, ताकि आपका सबसे मज़बूत प्रमाण पहले दिखे।	التعليم والمهارات والمشاريع قبل الخبرة، لتظهر أقوى أدلتك أولًا.
Serif typography, black headings and generous spacing; leadership and achievements up front.	सेरिफ़ फ़ॉन्ट, काले शीर्षक और खुली जगह; नेतृत्व और उपलब्धियाँ सबसे आगे।	خط مذيّل وعناوين سوداء وتباعد واسع؛ القيادة والإنجازات في المقدمة.
You have under 2 years of experience, so education, skills and projects lead the page.	आपका अनुभव 2 वर्ष से कम है, इसलिए शिक्षा, कौशल और प्रोजेक्ट पेज पर सबसे पहले हैं।	خبرتك أقل من سنتين، لذا يتصدر التعليم والمهارات والمشاريع الصفحة.
With 8+ years of experience, a senior layout puts leadership and achievements first.	8+ वर्ष के अनुभव के साथ, वरिष्ठ लेआउट नेतृत्व और उपलब्धियाँ पहले रखता है।	مع خبرة 8+ سنوات، يضع التخطيط القيادي القيادة والإنجازات أولًا.
A classic layout is the safest choice for this role and parses in every ATS.	इस भूमिका के लिए क्लासिक लेआउट सबसे सुरक्षित है और हर ATS में सही पढ़ा जाता है।	التخطيط الكلاسيكي هو الخيار الأكثر أمانًا لهذا الدور ويُقرأ في كل أنظمة ATS.
No answers captured yet.	अभी कोई उत्तर दर्ज नहीं हुआ।	لم تُسجَّل أي إجابات بعد.
User specific	उपयोगकर्ता-विशेष	خاص بالمستخدم
Logical Reasoning	तार्किक क्षमता	الاستدلال المنطقي
Quantitative Aptitude	मात्रात्मक योग्यता	القدرات الكمية
Verbal Ability	मौखिक क्षमता	القدرة اللفظية
No code submitted.	कोई कोड सबमिट नहीं हुआ।	لم يُسلَّم أي رمز.
No answer captured.	कोई उत्तर दर्ज नहीं हुआ।	لم تُسجَّل أي إجابة.
Unable to load interview context.	इंटरव्यू संदर्भ लोड नहीं हो सका।	تعذّر تحميل سياق المقابلة.
Entry level (0-2 years)	एंट्री लेवल (0-2 वर्ष)	مستوى مبتدئ (0-2 سنة)
Mid level (2-5 years)	मध्य स्तर (2-5 वर्ष)	مستوى متوسط (2-5 سنوات)
Senior (5+ years)	वरिष्ठ (5+ वर्ष)	خبير (5+ سنوات)
- Add target roles and skills on the dashboard.	- डैशबोर्ड पर लक्षित भूमिकाएँ और कौशल जोड़ें।	- أضف الأدوار المستهدفة والمهارات في لوحة التحكم.
Recent Interviews	हाल के इंटरव्यू	المقابلات الأخيرة
Unable to start interview.	इंटरव्यू शुरू नहीं हो सका।	تعذّر بدء المقابلة.
Unable to start interview. Please retry.	इंटरव्यू शुरू नहीं हो सका। कृपया फिर कोशिश करें।	تعذّر بدء المقابلة. يرجى المحاولة مجددًا.
Listening · pause-safe	सुन रहा है · रुकने पर भी सुरक्षित	يستمع · آمن عند التوقف
Speech recognition is not available in this browser. Type your answer and continue.	इस ब्राउज़र में स्पीच रिकग्निशन उपलब्ध नहीं है। अपना उत्तर लिखें और आगे बढ़ें।	التعرف على الكلام غير متاح في هذا المتصفح. اكتب إجابتك وتابع.
Interview completed. Building your performance scorecard.	इंटरव्यू पूरा हुआ। आपका प्रदर्शन स्कोरकार्ड बन रहा है।	اكتملت المقابلة. جارٍ إعداد بطاقة أدائك.
Unable to save interview.	इंटरव्यू सेव नहीं हो सका।	تعذّر حفظ المقابلة.
AI-assisted evaluation	AI-सहायता प्राप्त मूल्यांकन	تقييم بمساعدة الذكاء الاصطناعي
Evidence-based evaluation	प्रमाण-आधारित मूल्यांकन	تقييم قائم على الأدلة
Practice:	अभ्यास:	التدريب:
Target:	लक्ष्य:	الهدف:
Weaknesses	कमज़ोरियाँ	نقاط الضعف
Improvement areas	सुधार के क्षेत्र	مجالات التحسين
Performance dimensions	प्रदर्शन के आयाम	أبعاد الأداء
Preparation plan for your next interview	आपके अगले इंटरव्यू की तैयारी योजना	خطة التحضير لمقابلتك القادمة
See how your scores change day by day and week by week in	देखें कि आपके स्कोर दिन-ब-दिन और हफ़्ते-दर-हफ़्ते कैसे बदलते हैं:	اطّلع على تغيّر درجاتك يومًا بيوم وأسبوعًا بأسبوع في
Scorecard ready. Review your transcript and practice again when ready.	स्कोरकार्ड तैयार है। अपना ट्रांसक्रिप्ट देखें और तैयार होने पर फिर अभ्यास करें।	بطاقة النتائج جاهزة. راجع النص وتدرّب مجددًا عندما تكون مستعدًا.
Unable to load regional voices.	क्षेत्रीय आवाज़ें लोड नहीं हो सकीं।	تعذّر تحميل الأصوات الإقليمية.
Regional voice preview unavailable. Please retry.	क्षेत्रीय आवाज़ का प्रीव्यू उपलब्ध नहीं। कृपया फिर कोशिश करें।	معاينة الصوت الإقليمي غير متاحة. يرجى المحاولة مجددًا.
No matching regional female voice is installed.	कोई मेल खाती क्षेत्रीय महिला आवाज़ इंस्टॉल नहीं है।	لا يوجد صوت أنثوي إقليمي مطابق مثبّت.
Neural speech was unavailable; trying an installed browser voice.	न्यूरल स्पीच उपलब्ध नहीं थी; ब्राउज़र में इंस्टॉल आवाज़ आज़माई जा रही है।	الكلام العصبي غير متاح؛ تجربة صوت مثبّت في المتصفح.
Run sample tests	सैंपल टेस्ट चलाएँ	تشغيل الاختبارات النموذجية
Reset starter code	शुरुआती कोड रीसेट करें	إعادة الرمز الأولي
Example	उदाहरण	مثال
Input:	इनपुट:	المدخل:
Output:	आउटपुट:	المخرج:
Why:	क्यों:	السبب:
Write your solution, press "Run sample tests", then Submit.	अपना समाधान लिखें, "सैंपल टेस्ट चलाएँ" दबाएँ, फिर सबमिट करें।	اكتب حلك، واضغط "تشغيل الاختبارات النموذجية"، ثم سلّم.
This language is reviewed without running. Explain your approach in comments.	यह भाषा चलाए बिना जाँची जाती है। कमेंट में अपना तरीका समझाएँ।	تُراجع هذه اللغة دون تشغيل. اشرح طريقتك في التعليقات.
Tests run for Python, JavaScript and SQL only	टेस्ट केवल Python, JavaScript और SQL के लिए चलते हैं	تعمل الاختبارات لـ Python وJavaScript وSQL فقط
Starting Python (first run downloads about 10 MB)...	Python शुरू हो रहा है (पहली बार लगभग 10 MB डाउनलोड होगा)...	جارٍ تشغيل Python (يُنزّل أول تشغيل نحو 10 ميغابايت)...
Running tests...	टेस्ट चल रहे हैं...	جارٍ تشغيل الاختبارات...
Tests are not available for this language.	इस भाषा के लिए टेस्ट उपलब्ध नहीं हैं।	الاختبارات غير متاحة لهذه اللغة.
Could not run:	चला नहीं सका:	تعذّر التشغيل:
Query result matches	क्वेरी परिणाम मेल खाता है	نتيجة الاستعلام مطابقة
Query result differs: got	क्वेरी परिणाम अलग है: मिला	نتيجة الاستعلام مختلفة: الناتج
Sample tests (run in your browser):	सैंपल टेस्ट (आपके ब्राउज़र में चलते हैं):	الاختبارات النموذجية (تعمل في متصفحك):
Your code	आपका कोड	الرمز الخاص بك
One model solution	एक आदर्श समाधान	حل نموذجي
Was this feedback useful?	क्या यह फ़ीडबैक उपयोगी था?	هل كانت هذه الملاحظات مفيدة؟
Rate the feedback from 1 to 5	फ़ीडबैक को 1 से 5 तक रेट करें	قيّم الملاحظات من 1 إلى 5
The score or feedback seems unfair	स्कोर या फ़ीडबैक अनुचित लगता है	الدرجة أو الملاحظات تبدو غير عادلة
Thanks - your rating helps us improve the evaluator.	धन्यवाद - आपकी रेटिंग से मूल्यांकन बेहतर होता है।	شكرًا - تقييمك يساعدنا على تحسين المقيّم.
Could not save your rating.	आपकी रेटिंग सेव नहीं हो सकी।	تعذّر حفظ تقييمك.
This problem has no runnable entry point.	इस समस्या में चलाने योग्य शुरुआती फ़ंक्शन नहीं है।	لا تحتوي هذه المسألة على نقطة دخول قابلة للتشغيل.
Time limit exceeded. Check for an infinite loop or a very slow approach.	समय सीमा पार हो गई। अनंत लूप या बहुत धीमा तरीका तो नहीं, जाँचें।	تم تجاوز الحد الزمني. تحقق من وجود حلقة لا نهائية أو طريقة بطيئة جدًا.
The runner could not start. Check your internet connection.	रनर शुरू नहीं हो सका। अपना इंटरनेट कनेक्शन जाँचें।	تعذّر بدء المشغّل. تحقق من اتصالك بالإنترنت.
"""

# (English regex, Hindi template, Arabic template). $1 = captured value,
# translated when it is itself interface text; $L1 = a translated list.
PATTERNS = [
    (r"Signed in as (.+)", "$1 के रूप में साइन इन", "تم تسجيل الدخول باسم $1"),
    (r"Good morning, (.+)", "सुप्रभात, $1", "صباح الخير، $1"),
    (r"Good afternoon, (.+)", "नमस्कार, $1", "مساء الخير، $1"),
    (r"Good evening, (.+)", "शुभ संध्या, $1", "مساء الخير، $1"),
    (r"just now", "अभी", "الآن"),
    (r"(\d+) min ago", "$1 मिनट पहले", "قبل $1 دقيقة"),
    (r"(\d+) h ago", "$1 घंटे पहले", "قبل $1 ساعة"),
    (r"(\d+) days? ago", "$1 दिन पहले", "قبل $1 يوم"),
    (r"Your last run (.+?) found (\d+) job leads, (\d+) of them strong matches\.",
     "आपके पिछले रन ($1) में $2 जॉब लीड्स मिलीं, जिनमें $3 मज़बूत मिलान हैं।",
     "وجد آخر تشغيل لك ($1) $2 فرصة عمل، منها $3 تطابقات قوية."),
    (r"Your last run found (\d+) job leads, (\d+) of them strong matches\.",
     "आपके पिछले रन में $1 जॉब लीड्स मिलीं, जिनमें $2 मज़बूत मिलान हैं।",
     "وجد آخر تشغيل لك $1 فرصة عمل، منها $2 تطابقات قوية."),
    (r"Showing latest scheduled run from (.+)\.", "$1 का नवीनतम शेड्यूल्ड रन दिखाया जा रहा है।", "يُعرض آخر تشغيل مجدول من $1."),
    (r"ATS score (\d+) out of 100", "ATS स्कोर 100 में से $1", "درجة ATS ‏$1 من 100"),
    (r"Searching: (.+)", "खोज: $1", "البحث في: $1"),
    (r"(\d+) more job boards", "$1 और जॉब बोर्ड", "$1 مواقع وظائف أخرى"),
    (r"Saved resume: (.+)\. Choose a file only to replace it\.", "सेव किया रिज़्यूमे: $1। बदलने के लिए ही नई फ़ाइल चुनें।", "السيرة المحفوظة: $1. اختر ملفًا فقط لاستبدالها."),
    (r"Next run (.+)", "अगला रन $1", "التشغيل التالي $1"),
    (r"Runs daily at (.+) \((.+)\)\.", "हर दिन $1 बजे चलता है ($2)।", "يعمل يوميًا الساعة $1 ($2)."),
    (r"Raise your ATS score from (\d+)", "अपना ATS स्कोर $1 से बढ़ाएँ", "ارفع درجة ATS من $1"),
    (r"(\d+) specific improvements are ready\.", "$1 खास सुधार तैयार हैं।", "$1 تحسينات محددة جاهزة."),
    (r"Review (\d+) emails? waiting for your approval", "आपकी स्वीकृति की प्रतीक्षा में $1 ईमेल देखें", "راجع $1 رسائل بانتظار موافقتك"),
    (r"Practise for (.+)", "$1 के लिए अभ्यास करें", "تدرّب على $1"),
    (r"(.+): take a job-specific mock test\.", "$1: जॉब-विशेष मॉक टेस्ट दें।", "$1: خذ اختبارًا تجريبيًا خاصًا بالوظيفة."),
    (r"Showing (\d+) of (\d+) loaded leads \((\d+) found in this run\)\.", "लोड की गई $2 में से $1 लीड्स दिखाई जा रही हैं (इस रन में $3 मिलीं)।", "عرض $1 من $2 فرصة محمّلة ($3 وُجدت في هذا التشغيل)."),
    (r"Show more jobs \((\d+) remaining\)", "और नौकरियाँ दिखाएँ ($1 बाकी)", "عرض المزيد من الوظائف (متبقٍ $1)"),
    (r"Needs (\d+(?:\.\d+)?)-(\d+(?:\.\d+)?) yrs?", "$1-$2 वर्ष का अनुभव चाहिए", "تتطلب $1-$2 سنة"),
    (r"Needs (\d+) months\+", "$1+ महीने का अनुभव चाहिए", "تتطلب $1+ أشهر"),
    (r"Needs (\d+(?:\.\d+)?) yrs?\+", "$1+ वर्ष का अनुभव चाहिए", "تتطلب $1+ سنة"),
    (r"Needs (\d+(?:\.\d+)?)-(\d+) months", "$1-$2 महीने का अनुभव चाहिए", "تتطلب $1-$2 أشهر"),
    (r"Posted (.+)", "पोस्ट: $1", "نُشر: $1"),
    (r"Requires about (.+) years", "लगभग $1 वर्ष का अनुभव चाहिए", "تتطلب نحو $1 سنة"),
    (r"Link (.+)", "लिंक: $1", "الرابط: $1"),
    (r"unchecked", "जाँचा नहीं गया", "لم يُفحص"),
    (r"active", "सक्रिय", "نشط"),
    (r"(\d+)% \((.+)\)", "$1% ($2)", "$1% ($2)"),
    (r"(\d+) to (\d+)", "$1 से $2", "$1 إلى $2"),
    (r"Semantic provider: (.+)", "सिमेंटिक प्रदाता: $1", "مزوّد التحليل الدلالي: $1"),
    (r"not applicable", "लागू नहीं", "غير منطبق"),
    (r"(.+) profile", "$1 प्रोफ़ाइल", "ملف $1"),
    (r"Must-have skills found: (\d+)/(\d+)", "ज़रूरी कौशल मिले: $1/$2", "المهارات الأساسية الموجودة: $1/$2"),
    (r"Nice-to-have skills found: (\d+)/(\d+)", "अतिरिक्त कौशल मिले: $1/$2", "المهارات المرغوبة الموجودة: $1/$2"),
    (r"(.+) \((\d+(?:\.\d+)?)\+ years asked\)", "$1 ($2+ वर्ष माँगे गए)", "$1 (مطلوب $2+ سنة)"),
    (r"Degree asked: (.+) \((.+)\)", "माँगी गई डिग्री: $1 ($2)", "الشهادة المطلوبة: $1 ($2)"),
    (r"met", "पूरी", "مستوفاة"),
    (r"(\d+) page PDF, render and factual checks passed", "$1 पेज का PDF, रेंडर और तथ्य जाँच पास", "PDF من $1 صفحة، اجتاز فحص العرض والحقائق"),
    (r"\? page PDF, render and factual checks passed", "PDF, रेंडर और तथ्य जाँच पास", "PDF، اجتاز فحص العرض والحقائق"),
    (r"Validation needs review: (.+)", "सत्यापन की समीक्षा ज़रूरी: $1", "التحقق يحتاج إلى مراجعة: $1"),
    (r"Validation needs review", "सत्यापन की समीक्षा ज़रूरी", "التحقق يحتاج إلى مراجعة"),
    (r"Resume preparation failed: (.+)", "रिज़्यूमे तैयार करना विफल: $1", "فشل إعداد السيرة الذاتية: $1"),
    (r"Resume for (.+)", "$1 के लिए रिज़्यूमे", "سيرة ذاتية لـ $1"),
    (r"Supported by: (.+)", "प्रमाण: $1", "الدليل: $1"),
    (r"To (\S+), resume attached", "प्रति: $1, रिज़्यूमे संलग्न", "إلى: $1، السيرة مرفقة"),
    (r"To (\S+@\S+)", "प्रति: $1", "إلى: $1"),
    (r"Undo \((\d+)s\)", "पूर्ववत करें ($1 से.)", "تراجع ($1 ث)"),
    (r"Approved emails go out after (\d+) seconds unless you press Undo\. Today: (\d+) of (\d+) sent\. The same recruiter is not emailed twice within (\d+) days\.",
     "स्वीकृत ईमेल $1 सेकंड बाद भेजे जाते हैं, जब तक आप पूर्ववत न दबाएँ। आज: $3 में से $2 भेजे गए। एक ही रिक्रूटर को $4 दिनों में दो बार ईमेल नहीं किया जाता।",
     "تُرسل الرسائل المعتمدة بعد $1 ثانية ما لم تضغط تراجع. اليوم: أُرسل $2 من $3. لا يُراسل مسؤول التوظيف نفسه مرتين خلال $4 يومًا."),
    (r"Last scheduled run failed: (.+)", "पिछला शेड्यूल्ड रन विफल: $1", "فشل آخر تشغيل مجدول: $1"),
    (r"Latest (manual|scheduled) run: (.+), (\d+|n/a) jobs", "नवीनतम रन: $2, $3 नौकरियाँ", "آخر تشغيل: $2، $3 وظيفة"),
    (r"(\d+)s elapsed\. Usually under a minute; you can keep browsing\.", "$1 सेकंड बीते। आमतौर पर एक मिनट से कम; आप ब्राउज़ करते रह सकते हैं।", "مضت $1 ثانية. عادةً أقل من دقيقة؛ يمكنك مواصلة التصفح."),
    (r"Finished in (\d+)s\.", "$1 सेकंड में पूरा हुआ।", "اكتمل في $1 ثانية."),
    (r"Run complete: (\d+) job leads found\.", "रन पूरा: $1 जॉब लीड्स मिलीं।", "اكتمل التشغيل: وُجدت $1 فرصة عمل."),
    (r"Daily run scheduled for (.+)\.", "दैनिक रन $1 के लिए शेड्यूल किया गया।", "تمت جدولة التشغيل اليومي الساعة $1."),
    (r"(\d+) KB, ready to upload with the next run", "$1 KB, अगले रन के साथ अपलोड के लिए तैयार", "$1 كيلوبايت، جاهز للرفع مع التشغيل التالي"),
    (r"Fill in (.+)", "$1 भरें", "أدخل $1"),
    (r"Please fill in the required fields: (.+)\.", "कृपया ज़रूरी फ़ील्ड भरें: $L1।", "يرجى إكمال الحقول المطلوبة: $L1."),
    (r"Too many requests\. Please try again in about (\d+) minutes?\.", "बहुत ज़्यादा अनुरोध। कृपया लगभग $1 मिनट बाद फिर कोशिश करें।", "طلبات كثيرة جدًا. يرجى المحاولة بعد نحو $1 دقيقة."),
    (r"Request failed with status (\d+)\.", "अनुरोध विफल रहा (स्थिति $1)।", "فشل الطلب (الحالة $1)."),
    (r"Request failed \((\d+)\)", "अनुरोध विफल रहा ($1)", "فشل الطلب ($1)"),
    (r"OTP generated for local testing: (\d+)", "लोकल टेस्टिंग के लिए OTP: $1", "رمز للاختبار المحلي: $1"),
    (r"OTP sent to (.+)\. It expires in a few minutes\.", "OTP $1 पर भेजा गया। यह कुछ मिनटों में समाप्त हो जाएगा।", "أُرسل الرمز إلى $1. تنتهي صلاحيته خلال دقائق."),
    (r"Notice version (.+)\. Digital Personal Data Protection Act, 2023 \(India\)", "सूचना संस्करण $1। डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023 (भारत)", "إصدار الإشعار $1. قانون حماية البيانات الشخصية الرقمية لعام 2023 (الهند)"),
    (r"accounts with no sign-in for (\d+) days are deleted automatically\.", "जिन खातों में $1 दिनों तक साइन इन नहीं हुआ, वे अपने-आप डिलीट हो जाते हैं।", "تُحذف تلقائيًا الحسابات التي لم يُسجَّل الدخول إليها لمدة $1 يومًا."),
    (r"You accepted this notice \(version (.+)\) on (.+)\.", "आपने यह सूचना (संस्करण $1) $2 को स्वीकार की।", "قبلت هذا الإشعار (الإصدار $1) في $2."),
    (r"You have not accepted the current notice \(version (.+)\)\. Resume processing starts only after you accept it\.", "आपने मौजूदा सूचना (संस्करण $1) स्वीकार नहीं की है। इसे स्वीकार करने के बाद ही रिज़्यूमे प्रोसेस होगा।", "لم تقبل الإشعار الحالي (الإصدار $1). تبدأ معالجة السيرة بعد قبوله فقط."),
    (r"([+-]?\d+(?:\.\d+)?) pts vs previous period", "पिछली अवधि की तुलना में $1 अंक", "$1 نقطة مقارنة بالفترة السابقة"),
    (r"([+-]?\d+(?:\.\d+)?)% vs previous period", "पिछली अवधि की तुलना में $1%", "$1% مقارنة بالفترة السابقة"),
    (r"(\d+) practice days in this window", "इस अवधि में $1 अभ्यास दिन", "$1 أيام تدريب في هذه الفترة"),
    (r"(\d+) days?", "$1 दिन", "$1 يوم"),
    (r"(\d+) tests, (\d+) interviews", "$1 टेस्ट, $2 इंटरव्यू", "$1 اختبارات، $2 مقابلات"),
    (r"Completion: tests (.+), interviews (.+)", "पूर्णता: टेस्ट $1, इंटरव्यू $2", "الإكمال: الاختبارات $1، المقابلات $2"),
    (r"(\d+)/(\d+) correct", "$1/$2 सही", "$1/$2 صحيحة"),
    (r"(\d+) answered", "$1 उत्तर दिए", "تمت الإجابة على $1"),
    (r"Coding answers: (\d+), average (.+)/100", "कोडिंग उत्तर: $1, औसत $2/100", "إجابات البرمجة: $1، المتوسط $2/100"),
    (r"(quick|standard|full), (mixed|easy|medium|hard)", "$1, $2", "$1، $2"),
    (r"Week of (.+)", "$1 वाला सप्ताह", "أسبوع $1"),
    (r"Question (\d+) of (\d+)", "प्रश्न $1 / $2", "السؤال $1 من $2"),
    (r"Question (\d+) of (\d+) · Listening\.\.\.", "प्रश्न $1 / $2 · सुन रहा है...", "السؤال $1 من $2 · يستمع..."),
    (r"(\d+) · (\d+) of (\d+) answered", "$1 · $3 में से $2 उत्तर दिए", "$1 · تمت الإجابة على $2 من $3"),
    (r"You have (\d+) unanswered questions?\. Submit anyway\?", "$1 प्रश्नों के उत्तर बाकी हैं। फिर भी सबमिट करें?", "لديك $1 أسئلة بلا إجابة. هل تريد التسليم على أي حال؟"),
    (r"General practice: (.+)", "सामान्य अभ्यास: $1", "تدريب عام: $1"),
    (r"Could not submit: (.+)\. Your answers are saved; please try again\.", "सबमिट नहीं हो सका: $1। आपके उत्तर सेव हैं; कृपया फिर कोशिश करें।", "تعذّر التسليم: $1. إجاباتك محفوظة؛ يرجى المحاولة مجددًا."),
    (r"Microphone recognition stopped \((.+)\)\. Your captured text is preserved and you can continue typing\.", "माइक्रोफ़ोन पहचान रुक गई ($1)। दर्ज टेक्स्ट सुरक्षित है और आप लिखना जारी रख सकते हैं।", "توقف التعرف عبر الميكروفون ($1). النص الملتقط محفوظ ويمكنك متابعة الكتابة."),
    (r"Preparing (.+) preview\.\.\.", "$1 का प्रीव्यू तैयार हो रहा है...", "جارٍ إعداد معاينة $1..."),
    (r"Level: (.+)", "स्तर: $1", "المستوى: $1"),
    (r"Recommended for you: (.+)\.", "आपके लिए सुझाया गया: $1।", "موصى به لك: $1."),
    (r"Tailored resumes will use (.+)\.", "अनुकूलित रिज़्यूमे $1 टेम्पलेट में बनेंगे।", "ستستخدم السير المخصصة قالب $1."),
    (r"Template: (.+)", "टेम्पलेट: $1", "القالب: $1"),
    (r"Preview (.+)", "$1 का प्रीव्यू", "معاينة $1"),
    (r"For (.+) roles, recruiters scan your skills and projects first\.", "$1 भूमिकाओं में रिक्रूटर पहले आपके कौशल और प्रोजेक्ट देखते हैं।", "في أدوار $1، يطّلع مسؤولو التوظيف على مهاراتك ومشاريعك أولًا."),
    (r"A clean modern layout suits (.+) roles while staying fully ATS-readable\.", "साफ़ आधुनिक लेआउट $1 भूमिकाओं के लिए सही है और पूरी तरह ATS-पठनीय रहता है।", "يناسب التخطيط الحديث البسيط أدوار $1 ويبقى مقروءًا بالكامل لأنظمة ATS."),
    (r"Matched skills: (.+)", "मेल खाते कौशल: $1", "المهارات المطابقة: $1"),
    (r"Missing required skills: (.+)", "छूटे ज़रूरी कौशल: $1", "المهارات المطلوبة الناقصة: $1"),
    (r"(.+) female voice unavailable on this device\. Azure Speech is required for all six regional voices\.", "इस डिवाइस पर $1 महिला आवाज़ उपलब्ध नहीं। सभी छह क्षेत्रीय आवाज़ों के लिए Azure Speech ज़रूरी है।", "صوت $1 الأنثوي غير متاح على هذا الجهاز. يلزم Azure Speech لجميع الأصوات الإقليمية الستة."),
    (r"(.+) · Sarah · Neural voice configured", "$1 · सारा · न्यूरल आवाज़ सेट है", "$1 · سارة · الصوت العصبي مضبوط"),
    (r"(.+) · Sarah neural", "$1 · सारा न्यूरल", "$1 · سارة العصبية"),
    (r"Match (\d+) percent", "$1 प्रतिशत मिलान", "تطابق $1 بالمئة"),
    (r"Mark (.+) as not relevant", "$1 को अप्रासंगिक चिह्नित करें", "علّم $1 كغير مناسبة"),
    (r"(.+) \(opens in a new tab\)", "$1 (नए टैब में खुलता है)", "$1 (يفتح في علامة تبويب جديدة)"),
]

# Our own sentences that contain links or markup, swapped whole.
HTML = {
    "consent": (
        'मैं <a href="/privacy">गोपनीयता सूचना</a> से सहमत हूँ। मेरा रिज़्यूमे केवल उसे स्कोर करने, नौकरियाँ ढूँढने, रिज़्यूमे अनुकूलित करने और ड्राफ़्ट तैयार करने के लिए उपयोग होगा। रिक्रूटर ईमेल हर एक की मेरी स्वीकृति के बाद ही भेजे जाएँगे।',
        'أوافق على <a href="/privacy">إشعار الخصوصية</a>. تُستخدم سيرتي الذاتية فقط لتقييمها والعثور على الوظائف وتخصيص السير وإعداد المسودات. ولا تُرسل رسائل مسؤولي التوظيف إلا بعد موافقتي على كل واحدة.',
    ),
    "required-note": (
        '<span class="req">*</span> से चिह्नित फ़ील्ड ज़रूरी हैं।',
        'الحقول المعلَّمة بـ <span class="req">*</span> مطلوبة.',
    ),
}


def parse_rows() -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for number, line in enumerate(STRINGS.strip("\n").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not all(part.strip() for part in parts):
            raise ValueError(f"Row {number} needs English, Hindi and Arabic separated by tabs: {line!r}")
        english, hindi, arabic = (part.strip() for part in parts)
        rows[english] = (hindi, arabic)
    return rows


def build(output_dir: Path) -> None:
    rows = parse_rows()
    for index, (code, separator) in enumerate((("hi", ", "), ("ar", "، "))):
        pack = {
            "lang": code,
            "listSeparator": separator,
            "strings": {english: values[index] for english, values in rows.items()},
            "patterns": [[source, (hindi, arabic)[index]] for source, hindi, arabic in PATTERNS],
            "html": {key: values[index] for key, values in HTML.items()},
        }
        text = json.dumps(pack, ensure_ascii=False, indent=1, sort_keys=False)
        (output_dir / f"{code}.js").write_text(
            f"/* Generated by scripts/i18n_strings.py; edit that file, not this one. */\nwindow.JHA_I18N = {text};\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "src" / "job_hunting_agent" / "static" / "ui" / "i18n"
    target.mkdir(parents=True, exist_ok=True)
    build(target)
    print(f"Wrote {target / 'hi.js'} and {target / 'ar.js'} ({len(parse_rows())} strings, {len(PATTERNS)} patterns)")
