import { useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, Upload, X, Plus, MapPin, GraduationCap, BookOpen, User } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface ProfileData {
  name: string;
  age: string;
  university: string;
  course: string;
  location: string;
  subjects: string[];
  bio: string;
  photo?: string;
}

const popularSubjects = [
  "Высшая математика",
  "Программирование",
  "Физика",
  "Химия",
  "Английский язык",
  "Алгоритмы",
  "Базы данных",
  "Экономика",
  "Статистика",
  "Machine Learning",
  "Маркетинг",
  "Финансы",
];

export function ProfileSetup() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [profileData, setProfileData] = useState<ProfileData>({
    name: "",
    age: "",
    university: "",
    course: "",
    location: "",
    subjects: [],
    bio: "",
  });
  const [customSubject, setCustomSubject] = useState("");

  const totalSteps = 4;

  const handleNext = () => {
    if (step < totalSteps) {
      setStep(step + 1);
    } else {
      // Submit profile
      console.log("Profile data:", profileData);
      navigate("/discover");
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep(step - 1);
    } else {
      navigate("/");
    }
  };

  const toggleSubject = (subject: string) => {
    if (profileData.subjects.includes(subject)) {
      setProfileData({
        ...profileData,
        subjects: profileData.subjects.filter((s) => s !== subject),
      });
    } else {
      setProfileData({
        ...profileData,
        subjects: [...profileData.subjects, subject],
      });
    }
  };

  const addCustomSubject = () => {
    if (customSubject.trim() && !profileData.subjects.includes(customSubject.trim())) {
      setProfileData({
        ...profileData,
        subjects: [...profileData.subjects, customSubject.trim()],
      });
      setCustomSubject("");
    }
  };

  const handleCustomSubjectKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustomSubject();
    }
  };

  const canProceed = () => {
    switch (step) {
      case 1:
        return profileData.name && profileData.age;
      case 2:
        return profileData.university && profileData.course && profileData.location;
      case 3:
        return profileData.subjects.length > 0;
      case 4:
        return profileData.bio.length >= 20;
      default:
        return false;
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-secondary/10 to-accent/10" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(59,130,246,0.1),transparent_50%)]" />

      <div className="relative w-full max-w-2xl">
        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm text-muted-foreground">
              Шаг {step} из {totalSteps}
            </span>
            <span className="text-sm font-medium text-primary">
              {Math.round((step / totalSteps) * 100)}%
            </span>
          </div>
          <div className="h-2 bg-muted/30 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-primary to-secondary"
              initial={{ width: 0 }}
              animate={{ width: `${(step / totalSteps) * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>

        {/* Card */}
        <div className="bg-card backdrop-blur-xl border border-border rounded-3xl p-8 shadow-2xl">
          <AnimatePresence mode="wait">
            {/* Step 1: Basic Info */}
            {step === 1 && (
              <motion.div
                key="step1"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div className="p-3 bg-primary/10 rounded-2xl">
                    <User className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold">Основная информация</h2>
                    <p className="text-muted-foreground">Расскажите о себе</p>
                  </div>
                </div>

                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Как вас зовут? *
                    </label>
                    <input
                      type="text"
                      value={profileData.name}
                      onChange={(e) =>
                        setProfileData({ ...profileData, name: e.target.value })
                      }
                      placeholder="Введите ваше имя"
                      className="w-full px-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Сколько вам лет? *
                    </label>
                    <input
                      type="number"
                      value={profileData.age}
                      onChange={(e) =>
                        setProfileData({ ...profileData, age: e.target.value })
                      }
                      placeholder="18"
                      min="16"
                      max="99"
                      className="w-full px-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                    />
                  </div>

                  {/* Photo Upload */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Фото профиля
                    </label>
                    <div className="flex items-center justify-center w-full">
                      <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-border rounded-xl cursor-pointer hover:bg-muted/30 transition-all">
                        <Upload className="h-8 w-8 text-muted-foreground mb-2" />
                        <span className="text-sm text-muted-foreground">
                          Нажмите для загрузки
                        </span>
                        <input type="file" className="hidden" accept="image/*" />
                      </label>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 2: Education */}
            {step === 2 && (
              <motion.div
                key="step2"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div className="p-3 bg-secondary/10 rounded-2xl">
                    <GraduationCap className="h-6 w-6 text-secondary" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold">Образование</h2>
                    <p className="text-muted-foreground">Где вы учитесь?</p>
                  </div>
                </div>

                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Университет *
                    </label>
                    <input
                      type="text"
                      value={profileData.university}
                      onChange={(e) =>
                        setProfileData({
                          ...profileData,
                          university: e.target.value,
                        })
                      }
                      placeholder="МГУ, СПбГУ, МФТИ..."
                      className="w-full px-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Курс *
                    </label>
                    <select
                      value={profileData.course}
                      onChange={(e) =>
                        setProfileData({ ...profileData, course: e.target.value })
                      }
                      className="w-full px-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                    >
                      <option value="">Выберите курс</option>
                      <option value="1">1 курс</option>
                      <option value="2">2 курс</option>
                      <option value="3">3 курс</option>
                      <option value="4">4 курс</option>
                      <option value="5">5 курс</option>
                      <option value="магистратура">Магистратура</option>
                      <option value="аспирантура">Аспирантура</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Город *
                    </label>
                    <div className="relative">
                      <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                      <input
                        type="text"
                        value={profileData.location}
                        onChange={(e) =>
                          setProfileData({
                            ...profileData,
                            location: e.target.value,
                          })
                        }
                        placeholder="Москва, Санкт-Петербург..."
                        className="w-full pl-11 pr-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 3: Subjects */}
            {step === 3 && (
              <motion.div
                key="step3"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div className="p-3 bg-accent/10 rounded-2xl">
                    <BookOpen className="h-6 w-6 text-accent" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold">Предметы</h2>
                    <p className="text-muted-foreground">
                      Выберите предметы для изучения
                    </p>
                  </div>
                </div>

                {/* Add Custom Subject */}
                <div className="mb-6">
                  <label className="block text-sm font-medium mb-2">
                    Добавить свой предмет
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Plus className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                      <input
                        type="text"
                        value={customSubject}
                        onChange={(e) => setCustomSubject(e.target.value)}
                        onKeyDown={handleCustomSubjectKeyDown}
                        placeholder="Введите название предмета..."
                        className="w-full pl-11 pr-4 py-3 bg-muted/30 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                      />
                    </div>
                    <button
                      onClick={addCustomSubject}
                      disabled={!customSubject.trim()}
                      className="px-6 py-3 bg-gradient-to-r from-primary to-secondary text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-primary/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Добавить
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    💡 Нажмите Enter или кнопку "Добавить"
                  </p>
                </div>

                <div className="mb-4 flex justify-between items-center">
                  <p className="text-sm text-muted-foreground">
                    Выбрано: {profileData.subjects.length}
                  </p>
                  {profileData.subjects.length > 0 && (
                    <button
                      onClick={() => setProfileData({ ...profileData, subjects: [] })}
                      className="text-sm text-primary hover:text-primary/80 transition-colors"
                    >
                      Очистить всё
                    </button>
                  )}
                </div>

                {/* Selected Subjects (User's Custom + Popular) */}
                {profileData.subjects.length > 0 && (
                  <div className="mb-4">
                    <p className="text-sm font-medium mb-3">Выбранные предметы:</p>
                    <div className="flex flex-wrap gap-2">
                      {profileData.subjects.map((subject) => (
                        <button
                          key={subject}
                          onClick={() => toggleSubject(subject)}
                          className="px-4 py-2 rounded-full border-2 bg-primary border-primary text-white transition-all hover:opacity-80"
                        >
                          {subject}
                          <X className="inline h-4 w-4 ml-1" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Popular Subjects */}
                <div>
                  <p className="text-sm font-medium mb-3">Популярные предметы:</p>
                  <div className="flex flex-wrap gap-3 max-h-[300px] overflow-y-auto pr-2">
                    {popularSubjects.map((subject) => {
                      const isSelected = profileData.subjects.includes(subject);
                      return (
                        <button
                          key={subject}
                          onClick={() => toggleSubject(subject)}
                          className={`px-4 py-2 rounded-full border-2 transition-all ${
                            isSelected
                              ? "bg-muted/10 border-primary/30 text-muted-foreground opacity-50"
                              : "bg-muted/30 border-border hover:border-primary/50 hover:bg-primary/5"
                          }`}
                        >
                          {subject}
                          {isSelected && <X className="inline h-4 w-4 ml-1" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 4: Bio */}
            {step === 4 && (
              <motion.div
                key="step4"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div className="p-3 bg-primary/10 rounded-2xl">
                    <User className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold">О себе</h2>
                    <p className="text-muted-foreground">
                      Расскажите, почему хотите найти партнёра
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Биография * (минимум 20 символов)
                  </label>
                  <textarea
                    value={profileData.bio}
                    onChange={(e) =>
                      setProfileData({ ...profileData, bio: e.target.value })
                    }
                    placeholder="Например: Готовлюсь к экзаменам по математике, ищу партнёра для совместных занятий по утрам. Предпочитаю библиотеку..."
                    rows={6}
                    className="w-full px-4 py-3 bg-muted/30 border border-border rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                  />
                  <div className="flex justify-between items-center mt-2">
                    <p className="text-sm text-muted-foreground">
                      {profileData.bio.length} / 500
                    </p>
                    {profileData.bio.length >= 20 && (
                      <p className="text-sm text-green-500">✓ Отлично!</p>
                    )}
                  </div>
                </div>

                <div className="mt-6 p-4 bg-gradient-to-r from-primary/10 via-secondary/10 to-accent/10 border border-primary/20 rounded-xl">
                  <p className="text-sm text-muted-foreground">
                    💡 <strong>Совет:</strong> Опишите свои цели, предпочитаемое время и
                    место занятий. Это поможет найти идеального партнёра!
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Navigation Buttons */}
          <div className="flex gap-4 mt-8">
            <button
              onClick={handleBack}
              className="flex items-center gap-2 px-6 py-3 bg-muted/30 border border-border rounded-xl hover:bg-muted/50 transition-all"
            >
              <ArrowLeft className="h-5 w-5" />
              <span>Назад</span>
            </button>

            <button
              onClick={handleNext}
              disabled={!canProceed()}
              className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-primary to-secondary text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-primary/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
            >
              <span>{step === totalSteps ? "Завершить" : "Далее"}</span>
              {step < totalSteps && <ArrowRight className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}