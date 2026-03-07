import { useState } from "react";
import { Heart, X, MapPin, BookOpen, GraduationCap, Sparkles, Info } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

interface Profile {
  id: number;
  name: string;
  age: number;
  university: string;
  course: number;
  subjects: string[];
  bio: string;
  image: string;
  location: string;
}

const mockProfiles: Profile[] = [
  {
    id: 1,
    name: "Анна Смирнова",
    age: 20,
    university: "МГУ",
    course: 2,
    subjects: ["Высшая математика", "Программирование", "Физика"],
    bio: "Ищу партнёра для подготовки к экзаменам по математике. Предпочитаю утренние занятия в библиотеке.",
    image: "https://images.unsplash.com/photo-1758525866582-5c74fb7d9378?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHx5b3VuZyUyMHdvbWFuJTIwc3R1ZHlpbmclMjBib29rc3xlbnwxfHx8fDE3NzI4NzEzNjN8MA&ixlib=rb-4.1.0&q=80&w=1080",
    location: "Москва",
  },
  {
    id: 2,
    name: "Дмитрий Иванов",
    age: 21,
    university: "МФТИ",
    course: 3,
    subjects: ["Алгоритмы", "Базы данных", "Machine Learning"],
    bio: "Готовлюсь к собеседованиям в IT компании. Буду рад практиковать решение алгоритмических задач вместе!",
    image: "https://images.unsplash.com/photo-1688829388910-8c43a88d85a2?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxtYWxlJTIwc3R1ZGVudCUyMGxhcHRvcCUyMGxpYnJhcnl8ZW58MXx8fHwxNzcyODMxMDE5fDA&ixlib=rb-4.1.0&q=80&w=1080",
    location: "Долгопрудный",
  },
  {
    id: 3,
    name: "София Петрова",
    age: 19,
    university: "СПбГУ",
    course: 1,
    subjects: ["Английский язык", "Экономика", "Статистика"],
    bio: "Хочу найти напарника для практики разговорного английского и совместного решения задач по экономике.",
    image: "https://images.unsplash.com/photo-1573225117201-552324a6b253?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxmZW1hbGUlMjBzdHVkZW50JTIwY2FtcHVzJTIwYmFja3BhY2t8ZW58MXx8fHwxNzcyODcxMzY0fDA&ixlib=rb-4.1.0&q=80&w=1080",
    location: "Санкт-Петербург",
  },
  {
    id: 4,
    name: "Максим Новиков",
    age: 22,
    university: "НИУ ВШЭ",
    course: 4,
    subjects: ["Маркетинг", "Финансы", "Право"],
    bio: "Пишу диплом по маркетингу. Ищу единомышленников для обсуждения кейсов и взаимной мотивации.",
    image: "https://images.unsplash.com/photo-1594027554094-99c00129af63?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxzdHVkZW50JTIwc3R1ZHlpbmclMjB1bml2ZXJzaXR5fGVufDF8fHx8MTc3Mjg3MTM2Mnww&ixlib=rb-4.1.0&q=80&w=1080",
    location: "Москва",
  },
];

export function Discover() {
  const [profiles, setProfiles] = useState(mockProfiles);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showDetails, setShowDetails] = useState(false);

  const currentProfile = profiles[currentIndex];

  const handleLike = () => {
    handleSwipe("like");
  };

  const handleDislike = () => {
    handleSwipe("dislike");
  };

  const handleSwipe = (direction: "like" | "dislike") => {
    if (currentIndex < profiles.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setShowDetails(false);
    } else {
      // No more profiles
      setCurrentIndex(0);
    }
  };

  if (!currentProfile) {
    return (
      <div className="min-h-screen flex items-center justify-center pb-20 md:pb-0">
        <div className="text-center">
          <Sparkles className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2">Новых профилей пока нет</h2>
          <p className="text-muted-foreground">Загляните позже!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen py-8 pb-24 md:pb-8">
      <div className="max-w-md mx-auto px-4">
        {/* Header */}
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold mb-2">Открыть</h1>
          <p className="text-muted-foreground">
            {currentIndex + 1} / {profiles.length}
          </p>
        </div>

        {/* Card Stack */}
        <div className="relative h-[600px] mb-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentProfile.id}
              initial={{ scale: 0.9, opacity: 0, rotateY: -10 }}
              animate={{ scale: 1, opacity: 1, rotateY: 0 }}
              exit={{ scale: 0.9, opacity: 0, rotateY: 10 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0"
            >
              <div className="relative h-full rounded-3xl overflow-hidden bg-card backdrop-blur-xl border border-border shadow-2xl">
                {/* Image */}
                <div className="relative h-[400px] overflow-hidden">
                  <ImageWithFallback
                    src={currentProfile.image}
                    alt={currentProfile.name}
                    className="w-full h-full object-cover"
                  />
                  
                  {/* Gradient overlay */}
                  <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-transparent" />
                  
                  {/* Info button */}
                  <button
                    onClick={() => setShowDetails(!showDetails)}
                    className="absolute top-4 right-4 p-3 bg-background/80 backdrop-blur-xl rounded-full border border-border hover:bg-muted/80 transition-all"
                  >
                    <Info className="h-5 w-5" />
                  </button>
                </div>

                {/* Content */}
                <div className="absolute bottom-0 left-0 right-0 p-6">
                  <AnimatePresence>
                    {!showDetails ? (
                      <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.2 }}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <h2 className="text-3xl font-bold">
                            {currentProfile.name}
                          </h2>
                          <span className="text-2xl text-muted-foreground">
                            {currentProfile.age}
                          </span>
                        </div>

                        <div className="flex items-center gap-4 text-muted-foreground mb-4">
                          <div className="flex items-center gap-1">
                            <GraduationCap className="h-4 w-4" />
                            <span className="text-sm">
                              {currentProfile.university}, {currentProfile.course} курс
                            </span>
                          </div>
                          <div className="flex items-center gap-1">
                            <MapPin className="h-4 w-4" />
                            <span className="text-sm">{currentProfile.location}</span>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {currentProfile.subjects.slice(0, 3).map((subject, index) => (
                            <span
                              key={index}
                              className="px-3 py-1 bg-primary/10 border border-primary/20 rounded-full text-sm text-primary"
                            >
                              {subject}
                            </span>
                          ))}
                        </div>
                      </motion.div>
                    ) : (
                      <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.2 }}
                        className="max-h-[180px] overflow-y-auto"
                      >
                        <h3 className="text-lg font-bold mb-3 flex items-center gap-2">
                          <BookOpen className="h-5 w-5 text-primary" />
                          О себе
                        </h3>
                        <p className="text-muted-foreground mb-4 leading-relaxed">
                          {currentProfile.bio}
                        </p>

                        <h4 className="text-sm font-semibold mb-2">Предметы:</h4>
                        <div className="flex flex-wrap gap-2">
                          {currentProfile.subjects.map((subject, index) => (
                            <span
                              key={index}
                              className="px-3 py-1 bg-secondary/10 border border-secondary/20 rounded-full text-sm text-secondary"
                            >
                              {subject}
                            </span>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-center items-center gap-6">
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleDislike}
            className="flex items-center justify-center w-16 h-16 rounded-full bg-card backdrop-blur-xl border-2 border-destructive/50 text-destructive hover:bg-destructive/10 transition-all shadow-lg hover:shadow-destructive/20"
          >
            <X className="h-8 w-8" />
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleLike}
            className="flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-r from-primary to-secondary text-white hover:shadow-2xl hover:shadow-primary/50 transition-all"
          >
            <Heart className="h-10 w-10 fill-current" />
          </motion.button>
        </div>

        {/* Hint */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="text-center mt-8 text-sm text-muted-foreground"
        >
          Нажмите <Info className="inline h-4 w-4" /> чтобы узнать больше
        </motion.div>
      </div>
    </div>
  );
}
