import { Link } from "react-router";
import { MessageCircle, Calendar, BookOpen, Star } from "lucide-react";
import { motion } from "motion/react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

interface Match {
  id: number;
  name: string;
  university: string;
  subjects: string[];
  image: string;
  matchDate: string;
  lastMessage?: string;
  unread?: boolean;
}

const mockMatches: Match[] = [
  {
    id: 1,
    name: "Анна Смирнова",
    university: "МГУ",
    subjects: ["Высшая математика", "Программирование"],
    image: "https://images.unsplash.com/photo-1758525866582-5c74fb7d9378?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHx5b3VuZyUyMHdvbWFuJTIwc3R1ZHlpbmclMjBib29rc3xlbnwxfHx8fDE3NzI4NzEzNjN8MA&ixlib=rb-4.1.0&q=80&w=1080",
    matchDate: "2 часа назад",
    lastMessage: "Привет! Когда можем встретиться?",
    unread: true,
  },
  {
    id: 2,
    name: "Дмитрий Иванов",
    university: "МФТИ",
    subjects: ["Алгоритмы", "Базы данных"],
    image: "https://images.unsplash.com/photo-1688829388910-8c43a88d85a2?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxtYWxlJTIwc3R1ZGVudCUyMGxhcHRvcCUyMGxpYnJhcnl8ZW58MXx8fHwxNzcyODMxMDE5fDA&ixlib=rb-4.1.0&q=80&w=1080",
    matchDate: "Вчера",
    lastMessage: "Отлично! До встречи завтра",
    unread: false,
  },
  {
    id: 3,
    name: "София Петрова",
    university: "СПбГУ",
    subjects: ["Английский язык", "Экономика"],
    image: "https://images.unsplash.com/photo-1573225117201-552324a6b253?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxmZW1hbGUlMjBzdHVkZW50JTIwY2FtcHVzJTIwYmFja3BhY2t8ZW58MXx8fHwxNzcyODcxMzY0fDA&ixlib=rb-4.1.0&q=80&w=1080",
    matchDate: "3 дня назад",
  },
  {
    id: 4,
    name: "Максим Новиков",
    university: "НИУ ВШЭ",
    subjects: ["Маркетинг", "Финансы"],
    image: "https://images.unsplash.com/photo-1594027554094-99c00129af63?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxzdHVkZW50JTIwc3R1ZHlpbmclMjB1bml2ZXJzaXR5fGVufDF8fHx8MTc3Mjg3MTM2Mnww&ixlib=rb-4.1.0&q=80&w=1080",
    matchDate: "1 неделю назад",
    lastMessage: "Спасибо за совет!",
    unread: false,
  },
];

export function Matches() {
  return (
    <div className="min-h-screen py-8 pb-24 md:pb-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl md:text-4xl font-bold mb-2">Мои мэтчи</h1>
          <p className="text-muted-foreground">
            У вас {mockMatches.length} взаимных совпадений
          </p>
        </div>

        {/* New Matches Highlight */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 p-6 rounded-2xl bg-gradient-to-r from-primary/10 via-secondary/10 to-accent/10 border border-primary/20"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-full bg-primary/20">
              <Star className="h-5 w-5 text-primary" />
            </div>
            <h2 className="text-xl font-bold">Новые мэтчи!</h2>
          </div>
          <p className="text-muted-foreground">
            У вас {mockMatches.filter(m => m.unread).length} новое совпадение. 
            Начните общение первым!
          </p>
        </motion.div>

        {/* Matches List */}
        <div className="space-y-4">
          {mockMatches.map((match, index) => (
            <motion.div
              key={match.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <Link
                to={`/chat/${match.id}`}
                className="block group"
              >
                <div className="relative p-6 rounded-2xl bg-card backdrop-blur-xl border border-border hover:border-primary/50 transition-all hover:shadow-xl hover:shadow-primary/10">
                  {match.unread && (
                    <div className="absolute top-4 right-4 w-3 h-3 bg-primary rounded-full animate-pulse" />
                  )}

                  <div className="flex gap-4">
                    {/* Avatar */}
                    <div className="relative flex-shrink-0">
                      <div className="w-20 h-20 rounded-2xl overflow-hidden ring-2 ring-primary/20 group-hover:ring-primary/50 transition-all">
                        <ImageWithFallback
                          src={match.image}
                          alt={match.name}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="absolute -bottom-1 -right-1 p-1.5 bg-primary rounded-full">
                        <MessageCircle className="h-3 w-3 text-white" />
                      </div>
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <h3 className="text-xl font-bold mb-1 group-hover:text-primary transition-colors">
                            {match.name}
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            {match.university}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Calendar className="h-3 w-3" />
                          <span>{match.matchDate}</span>
                        </div>
                      </div>

                      {/* Subjects */}
                      <div className="flex flex-wrap gap-2 mb-3">
                        {match.subjects.map((subject, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-1 bg-secondary/10 border border-secondary/20 rounded-full text-xs text-secondary"
                          >
                            <BookOpen className="inline h-3 w-3 mr-1" />
                            {subject}
                          </span>
                        ))}
                      </div>

                      {/* Last Message */}
                      {match.lastMessage && (
                        <div className="flex items-center gap-2 text-sm">
                          <MessageCircle className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <p className={`truncate ${match.unread ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                            {match.lastMessage}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>

        {/* Empty State (if no matches) */}
        {mockMatches.length === 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center py-20"
          >
            <div className="inline-flex p-6 rounded-full bg-muted/50 mb-6">
              <Star className="h-12 w-12 text-muted-foreground" />
            </div>
            <h2 className="text-2xl font-bold mb-2">Пока нет мэтчей</h2>
            <p className="text-muted-foreground mb-8 max-w-md mx-auto">
              Продолжайте свайпать профили, чтобы найти партнёра для учёбы
            </p>
            <Link
              to="/discover"
              className="inline-block px-8 py-3 bg-gradient-to-r from-primary to-secondary rounded-full text-white font-semibold hover:shadow-lg hover:shadow-primary/50 transition-all"
            >
              Найти партнёров
            </Link>
          </motion.div>
        )}
      </div>
    </div>
  );
}
