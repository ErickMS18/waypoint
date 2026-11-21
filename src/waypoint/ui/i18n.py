"""UI strings in Portuguese and English. `t(key, **kw)` formats the string in the current language."""
from __future__ import annotations

from datetime import date
from typing import Any

LANG = {"lang": "pt"}

S: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- shell / navigation
    "app_tagline": {"pt": "Carreira, estudos e projetos num lugar só", "en": "Career, study and projects in one place"},
    "sec_plan": {"pt": "Planejar", "en": "Plan"},
    "sec_market": {"pt": "Mercado", "en": "Market"},
    "sec_you": {"pt": "Você", "en": "You"},
    "nav_today": {"pt": "Hoje", "en": "Today"},
    "nav_week": {"pt": "Semana", "en": "Week"},
    "nav_projects": {"pt": "Projetos", "en": "Projects"},
    "nav_plan": {"pt": "Plano de estudos", "en": "Study plan"},
    "nav_market": {"pt": "Visão do mercado", "en": "Market overview"},
    "nav_compare": {"pt": "Comparar cargos", "en": "Compare roles"},
    "nav_jobs": {"pt": "Vagas", "en": "Jobs"},
    "nav_roles": {"pt": "Cargos", "en": "Roles"},
    "nav_profile": {"pt": "Meu perfil", "en": "My profile"},
    "nav_report": {"pt": "Relatório e post", "en": "Report & post"},
    "theme": {"pt": "Tema", "en": "Theme"},
    "theme_dark": {"pt": "Escuro", "en": "Dark"},
    "theme_light": {"pt": "Claro", "en": "Light"},
    "language": {"pt": "Idioma", "en": "Language"},
    "last_update": {"pt": "Mercado atualizado: **{when}**", "en": "Market updated: **{when}**"},
    "never": {"pt": "nunca", "en": "never"},
    "update_all": {"pt": "Atualizar mercado", "en": "Update market"},
    "update_help": {"pt": "Coleta vagas novas, extrai as skills, refaz o plano e os relatórios. Roda em segundo plano.",
                    "en": "Collects new postings, extracts skills, rebuilds the plan and reports. Runs in the background."},
    "updating_since": {"pt": "Começou {when}. Pode fechar o navegador: continua sozinho.",
                       "en": "Started {when}. You can close the browser: it keeps going."},
    "updating": {"pt": "Atualizando…", "en": "Updating…"},
    "update_failed": {"pt": "A última atualização falhou: {err}. Detalhes em data/logs/update.log.",
                      "en": "The last update failed: {err}. Details in data/logs/update.log."},
    "update_done_toast": {"pt": "Mercado atualizado ✓", "en": "Market updated ✓"},
    "status_line": {"pt": "{n} vagas · {r} cargos · IA: {ai}", "en": "{n} postings · {r} roles · AI: {ai}"},
    "no_key": {"pt": "sem chave (dicionário)", "en": "no key (dictionary)"},
    "options": {"pt": "Opções", "en": "Options"},
    "auto_update": {"pt": "Atualizar o mercado ao abrir pelo atalho", "en": "Update the market when opened from the shortcut"},
    "auto_update_help": {"pt": "Se a última atualização tiver mais de ~1 dia.", "en": "If the last update is more than ~1 day old."},
    "shutdown": {"pt": "Encerrar Waypoint", "en": "Quit Waypoint"},
    "shutdown_help": {"pt": "Desliga a interface. Para abrir de novo, use o atalho.",
                      "en": "Stops the app. Use the shortcut to open it again."},
    "shutdown_done": {"pt": "Waypoint encerrado. Pode fechar esta aba.", "en": "Waypoint stopped. You can close this tab."},
    "saved": {"pt": "Salvo ✓", "en": "Saved ✓"},
    "cancel": {"pt": "Cancelar", "en": "Cancel"},
    "confirm": {"pt": "Confirmar", "en": "Confirm"},
    "save": {"pt": "Salvar", "en": "Save"},
    "delete": {"pt": "Excluir", "en": "Delete"},
    "undo": {"pt": "Desfazer", "en": "Undo"},
    "hours_short": {"pt": "h", "en": "h"},
    "no_data_market": {"pt": "Ainda não há vagas analisadas. Clique em **Atualizar mercado** na barra lateral (leva alguns minutos).",
                       "en": "No postings analyzed yet. Click **Update market** in the sidebar (takes a few minutes)."},

    # ---------------------------------------------------------------- areas / focus
    "area_faculdade": {"pt": "Faculdade", "en": "College"},
    "area_estagio": {"pt": "Estágio / trabalho", "en": "Internship / work"},
    "area_pesquisa": {"pt": "Pesquisa", "en": "Research"},
    "area_pessoal": {"pt": "Pessoal", "en": "Personal"},
    "area_carreira": {"pt": "Carreira", "en": "Career"},
    "area_exploracao": {"pt": "Exploração", "en": "Exploration"},
    "area_interesses": {"pt": "Interesses", "en": "Interests"},
    "prio_1": {"pt": "Alta", "en": "High"},
    "prio_2": {"pt": "Normal", "en": "Normal"},
    "prio_3": {"pt": "Baixa", "en": "Low"},

    # ---------------------------------------------------------------- today
    "today_title": {"pt": "Hoje", "en": "Today"},
    "greet_morning": {"pt": "Bom dia", "en": "Good morning"},
    "greet_afternoon": {"pt": "Boa tarde", "en": "Good afternoon"},
    "greet_evening": {"pt": "Boa noite", "en": "Good evening"},
    "now_label": {"pt": "Agora", "en": "Now"},
    "now_empty": {"pt": "Nada planejado para agora.", "en": "Nothing planned right now."},
    "day_done": {"pt": "Dia concluído. Bom trabalho! 🎉", "en": "Day done. Nice work! 🎉"},
    "done_btn": {"pt": "Concluí · {h}", "en": "Done · {h}"},
    "partial_btn": {"pt": "Fiz uma parte", "en": "Did part of it"},
    "partial_hours": {"pt": "Quantas horas você fez?", "en": "How many hours did you do?"},
    "partial_save": {"pt": "Registrar", "en": "Log it"},
    "skip_btn": {"pt": "Próximo", "en": "Next"},
    "skip_help": {"pt": "Não dá agora? Mostra o próximo bloco; este continua no plano.",
                  "en": "Can't do it now? Shows the next block; this one stays in the plan."},
    "logged_toast": {"pt": "Registrado: {h} em {what}", "en": "Logged: {h} on {what}"},
    "undo_last": {"pt": "Desfazer último registro", "en": "Undo last entry"},
    "undone_toast": {"pt": "Registro desfeito", "en": "Entry undone"},
    "goal_today": {"pt": "Meta de hoje: {done} de {total}", "en": "Today's goal: {done} of {total}"},
    "rest_of_day": {"pt": "Resto do dia", "en": "Rest of the day"},
    "done_today": {"pt": "Feito hoje", "en": "Done today"},
    "free_today": {"pt": "Tempo livre hoje", "en": "Free time today"},
    "free_today_help": {"pt": "Mudou o dia? Ajuste e o plano se refaz na hora.",
                        "en": "Day changed? Adjust it and the plan is rebuilt instantly."},
    "slipped": {"pt": "Ficou pendente de {day}: {items}. Já redistribuí na semana.",
                "en": "Left over from {day}: {items}. Already spread over the week."},
    "risk": {"pt": "**{task}** ({project}) vence {due} e faltam **{h}** que não cabem no seu tempo livre.",
             "en": "**{task}** ({project}) is due {due} and **{h}** don't fit in your free time."},
    "risk_borrow": {"pt": "Usar {h} de {foco} desta semana", "en": "Use {h} of this week's {foco}"},
    "risk_borrow_help": {"pt": "Troca consciente: menos estudo de {foco} nesta semana para salvar o prazo. A exploração nunca é usada.",
                         "en": "Deliberate trade-off: less {foco} study this week to save the deadline. Exploration is never used."},
    "risk_hours": {"pt": "Aumentar meu tempo livre", "en": "Add free time"},
    "risk_scope": {"pt": "Rever prazo ou escopo", "en": "Review deadline or scope"},
    "borrow_toast": {"pt": "Combinado: {h} de {foco} vão para {task} nesta semana.",
                     "en": "Done: {h} of {foco} go to {task} this week."},
    "overdue": {"pt": "Atrasado", "en": "Overdue"},
    "due_today": {"pt": "vence hoje", "en": "due today"},
    "due_tomorrow": {"pt": "vence amanhã", "en": "due tomorrow"},
    "due_in": {"pt": "vence em {n} dias", "en": "due in {n} days"},
    "due_on": {"pt": "em {date}", "en": "on {date}"},
    "late_by": {"pt": "atrasado {n} dia(s)", "en": "{n} day(s) late"},
    "empty_today_title": {"pt": "Vamos montar sua semana", "en": "Let's build your week"},
    "empty_today": {"pt": "O Waypoint junta o seu plano de estudos com os seus projetos e prazos e diz o que fazer agora. "
                          "Comece cadastrando o que está em andamento.",
                    "en": "Waypoint combines your study plan with your projects and deadlines and tells you what to do now. "
                          "Start by adding what you are working on."},
    "cta_add_project": {"pt": "Adicionar um projeto", "en": "Add a project"},
    "cta_make_plan": {"pt": "Gerar plano de estudos", "en": "Generate study plan"},
    "cta_set_time": {"pt": "Definir meu tempo livre", "en": "Set my free time"},
    "week_glance": {"pt": "Sua semana", "en": "Your week"},
    "week_glance_help": {"pt": "Horas planejadas por área, de hoje até domingo.", "en": "Planned hours by area, today to Sunday."},
    "see_week": {"pt": "Ver a semana", "en": "Open the week"},
    "market_pulse": {"pt": "Pulso do mercado", "en": "Market pulse"},
    "fit_label": {"pt": "Sua aderência", "en": "Your fit"},
    "fit_help": {"pt": "Quanto das skills mais pedidas (ponderadas pela demanda) você já cobre. Nível 2 = cobre.",
                 "en": "How much of the most requested skills (weighted by demand) you already cover. Level 2 = covered."},
    "top_gap": {"pt": "Maior lacuna", "en": "Top gap"},
    "postings": {"pt": "Vagas analisadas", "en": "Postings analyzed"},
    "companies": {"pt": "Empresas", "en": "Companies"},
    "active_roles": {"pt": "Cargos ativos", "en": "Active roles"},
    "onboarding": {"pt": "Primeiros passos", "en": "Getting started"},
    "ob_key": {"pt": "Chave de IA no arquivo .env", "en": "AI key in the .env file"},
    "ob_key_how": {"pt": "Opcional, mas melhora muito a leitura das vagas. Crie uma chave gratuita do Gemini em aistudio.google.com e coloque `GEMINI_API_KEY=...` no arquivo `.env`.",
                   "en": "Optional, but it makes reading postings much better. Create a free Gemini key at aistudio.google.com and put `GEMINI_API_KEY=...` in the `.env` file."},
    "ob_cv": {"pt": "Seu currículo", "en": "Your resume"},
    "ob_cv_how": {"pt": "Envie em **Meu perfil**. Fica só no seu computador.", "en": "Upload it in **My profile**. It stays on your computer."},
    "ob_data": {"pt": "Primeira atualização do mercado", "en": "First market update"},
    "ob_data_how": {"pt": "Clique em **Atualizar mercado** na barra lateral.", "en": "Click **Update market** in the sidebar."},
    "ob_projects": {"pt": "Seus projetos e prazos", "en": "Your projects and deadlines"},
    "ob_projects_how": {"pt": "Cadastre em **Projetos** (faculdade, estágio, pesquisa…).", "en": "Add them in **Projects** (college, internship, research…)."},

    # ---------------------------------------------------------------- week
    "week_title": {"pt": "Semana", "en": "Week"},
    "week_sub": {"pt": "Prazos primeiro e espalhados, estudo reservado, exploração protegida. Tudo se refaz quando você registra progresso.",
                 "en": "Deadlines first and spread out, study reserved, exploration protected. Everything is rebuilt when you log progress."},
    "this_week": {"pt": "Esta semana", "en": "This week"},
    "next_week": {"pt": "Próxima semana", "en": "Next week"},
    "free_of": {"pt": "{p} de {c}", "en": "{p} of {c}"},
    "nothing_day": {"pt": "Livre", "en": "Free"},
    "past_day": {"pt": "Passou", "en": "Past"},
    "next_week_note": {"pt": "O estudo da próxima semana entra quando ela começar; aqui aparecem os prazos já encaixados.",
                       "en": "Next week's study is added when the week starts; here you see the deadlines already placed."},
    "availability": {"pt": "Meu tempo livre", "en": "My free time"},
    "availability_sub": {"pt": "Horas livres em cada dia da semana (fora aulas, estágio e descanso).",
                         "en": "Free hours on each weekday (outside classes, work and rest)."},
    "overrides": {"pt": "Dias diferentes do normal", "en": "Days that differ from usual"},
    "override_day": {"pt": "Dia", "en": "Day"},
    "override_hours": {"pt": "Horas livres nesse dia", "en": "Free hours that day"},
    "override_add": {"pt": "Adicionar exceção", "en": "Add exception"},
    "max_block": {"pt": "Bloco máximo por tarefa num dia (h)", "en": "Max block per task per day (h)"},
    "load_by_area": {"pt": "Carga da semana por área", "en": "Week load by area"},
    "unscheduled_study": {"pt": "{h} de estudo não couberam nesta semana. Aumente seu tempo livre ou reduza as horas do plano.",
                          "en": "{h} of study didn't fit this week. Add free time or reduce the plan's hours."},

    # ---------------------------------------------------------------- projects
    "projects_title": {"pt": "Projetos", "en": "Projects"},
    "projects_sub": {"pt": "Tudo o que disputa o seu tempo: faculdade, estágio, pesquisa, pessoal. O Waypoint encaixa na semana.",
                     "en": "Everything competing for your time: college, work, research, personal. Waypoint fits it into the week."},
    "new_project": {"pt": "Novo projeto", "en": "New project"},
    "p_name": {"pt": "Nome", "en": "Name"},
    "p_name_ph": {"pt": "ex.: TDE de Banco de Dados", "en": "e.g. Database course assignment"},
    "p_area": {"pt": "Área", "en": "Area"},
    "p_has_deadline": {"pt": "Tem prazo", "en": "Has a deadline"},
    "p_deadline": {"pt": "Prazo", "en": "Deadline"},
    "p_priority": {"pt": "Prioridade", "en": "Priority"},
    "p_hours": {"pt": "Esforço estimado (horas)", "en": "Estimated effort (hours)"},
    "p_hours_help": {"pt": "Um chute está ótimo. Dá para ajustar depois, por tarefa.", "en": "A rough guess is fine. You can adjust per task later."},
    "p_notes": {"pt": "O que precisa ser entregue? (opcional)", "en": "What needs to be delivered? (optional)"},
    "p_breakdown": {"pt": "Quebrar em tarefas com IA", "en": "Break into tasks with AI"},
    "p_breakdown_help": {"pt": "A IA sugere tarefas concretas com horas; você edita depois. Sem chave, uso um modelo simples.",
                         "en": "AI suggests concrete tasks with hours; you edit them later. Without a key, a simple template is used."},
    "p_create": {"pt": "Criar projeto", "en": "Create project"},
    "p_created": {"pt": "Projeto criado: {name}", "en": "Project created: {name}"},
    "p_name_required": {"pt": "Dê um nome ao projeto.", "en": "Give the project a name."},
    "p_progress": {"pt": "{done} de {total} feitas", "en": "{done} of {total} done"},
    "p_no_deadline": {"pt": "sem prazo", "en": "no deadline"},
    "p_tasks": {"pt": "Tarefas", "en": "Tasks"},
    "t_title": {"pt": "Tarefa", "en": "Task"},
    "t_hours": {"pt": "Horas", "en": "Hours"},
    "t_due": {"pt": "Prazo próprio", "en": "Own due date"},
    "t_done": {"pt": "Feita", "en": "Done"},
    "t_logged": {"pt": "Já feito (h)", "en": "Logged (h)"},
    "p_save_tasks": {"pt": "Salvar tarefas", "en": "Save tasks"},
    "p_archive": {"pt": "Arquivar", "en": "Archive"},
    "p_unarchive": {"pt": "Reativar", "en": "Restore"},
    "p_delete_confirm": {"pt": "Excluir **{name}** e o histórico dele? Não dá para desfazer.",
                         "en": "Delete **{name}** and its history? This can't be undone."},
    "p_deleted": {"pt": "Projeto excluído", "en": "Project deleted"},
    "p_empty": {"pt": "Nenhum projeto ainda. Crie o primeiro acima — pode ser um trabalho da faculdade, uma entrega do estágio ou algo pessoal.",
                "en": "No projects yet. Create the first one above — a college assignment, a work deliverable or something personal."},
    "p_archived": {"pt": "Arquivados ({n})", "en": "Archived ({n})"},
    "p_edit": {"pt": "Editar detalhes", "en": "Edit details"},

    # ---------------------------------------------------------------- study plan
    "plan_title": {"pt": "Plano de estudos", "en": "Study plan"},
    "focus_weights": {"pt": "Focos e pesos", "en": "Focus & weights"},
    "focus_help": {"pt": "Os pesos dividem suas horas de estudo. A exploração é protegida: nunca é cortada para encaixar outra coisa.",
                   "en": "Weights split your study hours. Exploration is protected: it is never cut to fit something else."},
    "hours_week": {"pt": "Horas de estudo por semana", "en": "Study hours per week"},
    "explore_topics": {"pt": "O que você quer explorar (vírgulas)", "en": "What you want to explore (commas)"},
    "interests": {"pt": "Interesses pessoais (vírgulas)", "en": "Personal interests (commas)"},
    "interests_help": {"pt": "Ex.: violão, astrologia. O plano procura pontes entre eles e a carreira.",
                       "en": "E.g. guitar, astronomy. The plan looks for bridges between them and your career."},
    "protect_explore": {"pt": "Proteger as horas de exploração", "en": "Protect exploration hours"},
    "weights_sum": {"pt": "Os pesos somam {s}. Vou normalizar para 100 ao salvar.", "en": "Weights add up to {s}. They will be normalized to 100 on save."},
    "save_focus": {"pt": "Salvar focos", "en": "Save focus"},
    "focus_saved": {"pt": "Focos salvos. Gere o plano de novo para aplicar.", "en": "Focus saved. Regenerate the plan to apply it."},
    "gen_plan": {"pt": "Gerar plano", "en": "Generate plan"},
    "gen_plan_ai": {"pt": "Pedir ideias de projetos à IA", "en": "Ask the AI for project ideas"},
    "plan_generating": {"pt": "Montando o plano…", "en": "Building the plan…"},
    "plan_needs_data": {"pt": "O plano precisa de vagas analisadas. Clique em **Atualizar mercado**.",
                        "en": "The plan needs analyzed postings. Click **Update market**."},
    "plan_lang_mismatch": {"pt": "Este plano foi gerado em inglês. Gere de novo para ver tudo em português.",
                           "en": "This plan was generated in Portuguese. Regenerate it to see everything in English."},
    "generated_at": {"pt": "Gerado em {when}. É refeito a cada atualização do mercado.", "en": "Generated on {when}. Rebuilt on every market update."},
    "study_week": {"pt": "Estudo desta semana", "en": "This week's study"},
    "study_week_help": {"pt": "Esses blocos já aparecem em Hoje e Semana. Registre o progresso por lá.",
                        "en": "These blocks already show up in Today and Week. Log progress there."},
    "career_prios": {"pt": "Prioridades de carreira", "en": "Career priorities"},
    "career_prios_help": {"pt": "Ordem = quanto o mercado pede × quanto falta para você.", "en": "Order = market demand × how much you are missing."},
    "you_status": {"pt": "Você: {s} · ~{h} de estudo", "en": "You: {s} · ~{h} of study"},
    "pairs": {"pt": "Vem junto com: {x}", "en": "Often paired with: {x}"},
    "suggested_projects": {"pt": "Projetos sugeridos", "en": "Suggested projects"},
    "suggested_projects_help": {"pt": "Um projeto bem feito cobre várias lacunas de uma vez e vira portfólio. Dá para mandar direto para seus projetos.",
                                "en": "One good project closes several gaps at once and becomes portfolio. You can send it straight to your projects."},
    "deliverable": {"pt": "Entrega", "en": "Deliverable"},
    "bridge_with": {"pt": "Ponte com: {x}", "en": "Bridge with: {x}"},
    "add_to_projects": {"pt": "Adicionar aos meus projetos", "en": "Add to my projects"},
    "exploration": {"pt": "Exploração", "en": "Exploration"},
    "explore_empty": {"pt": "Adicione tópicos em Focos e pesos.", "en": "Add topics in Focus & weights."},
    "interests_bridges": {"pt": "Interesses e pontes", "en": "Interests & bridges"},
    "interests_empty": {"pt": "Adicione interesses em Focos e pesos.", "en": "Add interests in Focus & weights."},
    "tradeoffs": {"pt": "Trade-offs (você decide)", "en": "Trade-offs (your call)"},
    "status_has": {"pt": "tem", "en": "have"},
    "status_partial": {"pt": "parcial", "en": "partial"},
    "status_missing": {"pt": "falta", "en": "missing"},

    # ---------------------------------------------------------------- market
    "market_title": {"pt": "Visão do mercado", "en": "Market overview"},
    "role": {"pt": "Cargo", "en": "Role"},
    "all": {"pt": "Todos", "en": "All"},
    "region": {"pt": "Região", "en": "Region"},
    "all_regions": {"pt": "(todas)", "en": "(all)"},
    "seniority": {"pt": "Senioridade", "en": "Seniority"},
    "any": {"pt": "todas", "en": "any"},
    "how_many_skills": {"pt": "Quantas skills mostrar", "en": "How many skills"},
    "m_jobs": {"pt": "Vagas", "en": "Postings"},
    "m_companies": {"pt": "Empresas", "en": "Companies"},
    "m_skills": {"pt": "Skills distintas", "en": "Distinct skills"},
    "m_remote": {"pt": "Remoto", "en": "Remote"},
    "no_jobs_filter": {"pt": "Nenhuma vaga com esses filtros.", "en": "No postings match these filters."},
    "top_skills": {"pt": "Skills mais pedidas", "en": "Most requested skills"},
    "top_skills_help": {"pt": "Clique numa barra para ver as vagas que pedem aquela skill.",
                        "en": "Click a bar to see the postings that ask for that skill."},
    "required": {"pt": "Obrigatória", "en": "Required"},
    "nice": {"pt": "Diferencial", "en": "Nice-to-have"},
    "share_postings": {"pt": "% das vagas", "en": "% of postings"},
    "n_postings": {"pt": "nº vagas", "en": "# postings"},
    "total_share": {"pt": "% total", "en": "% total"},
    "see_jobs_asking": {"pt": "Ver vagas que pedem", "en": "Show postings asking for"},
    "how_asked": {"pt": "Como pede", "en": "Asked as"},
    "company": {"pt": "Empresa", "en": "Company"},
    "title": {"pt": "Título", "en": "Title"},
    "link": {"pt": "Link", "en": "Link"},
    "open": {"pt": "abrir", "en": "open"},
    "level": {"pt": "Nível", "en": "Level"},
    "not_informed": {"pt": "não informado", "en": "not stated"},
    "trends": {"pt": "Em alta", "en": "Trending"},
    "trends_empty": {"pt": "Precisa de pelo menos 10 vagas recentes e 10 antigas com data. Conforme você atualiza ao longo das semanas, isto aparece.",
                     "en": "Needs at least 10 recent and 10 older dated postings. It shows up as you update over the weeks."},
    "recent": {"pt": "Recentes", "en": "Recent"},
    "older": {"pt": "Antigas", "en": "Older"},
    "br_vs_intl": {"pt": "Brasil × internacional", "en": "Brazil × international"},
    "full_table": {"pt": "Tabela completa", "en": "Full table"},
    "category": {"pt": "Categoria", "en": "Category"},
    "few_jobs_role": {"pt": "Só {n} vaga(s): os números deste cargo ainda são instáveis.",
                      "en": "Only {n} posting(s): this role's numbers are still unstable."},

    # ---------------------------------------------------------------- compare
    "compare_title": {"pt": "Comparar cargos", "en": "Compare roles"},
    "compare_pick": {"pt": "Cargos (até 3)", "en": "Roles (up to 3)"},
    "compare_ph": {"pt": "Escolha os cargos", "en": "Pick roles"},
    "compare_need2": {"pt": "Precisa de vagas de pelo menos dois cargos. Ative mais cargos em **Cargos** e atualize.",
                      "en": "Needs postings for at least two roles. Turn on more roles in **Roles** and update."},
    "pick_two": {"pt": "Escolha pelo menos dois.", "en": "Pick at least two."},
    "entry_level": {"pt": "Estágio/júnior", "en": "Intern/junior"},
    "typical": {"pt": "Mais típicas deste cargo", "en": "Most typical of this role"},
    "same_skills": {"pt": "Mesmas skills, cargos diferentes", "en": "Same skills, different roles"},
    "same_skills_help": {"pt": "Cada ponto é a % das vagas daquele cargo que citam a skill. Quanto mais longe os pontos, mais a skill diferencia os cargos.",
                         "en": "Each dot is the % of that role's postings that mention the skill. The farther apart, the more the skill sets the roles apart."},
    "as_table": {"pt": "Ver como tabela", "en": "View as table"},

    # ---------------------------------------------------------------- jobs
    "jobs_title": {"pt": "Vagas", "en": "Jobs"},
    "search": {"pt": "Buscar no título ou empresa", "en": "Search title or company"},
    "search_ph": {"pt": "ex.: júnior, Nubank, LLM", "en": "e.g. junior, Nubank, LLM"},
    "that_ask": {"pt": "Que pedem as skills", "en": "Asking for skills"},
    "whatever": {"pt": "qualquer", "en": "any"},
    "n_jobs_click": {"pt": "{n} vagas · clique numa linha para ver os detalhes", "en": "{n} postings · click a row for details"},
    "published": {"pt": "Publicada", "en": "Published"},
    "source": {"pt": "fonte", "en": "source"},
    "required_pl": {"pt": "Obrigatórias", "en": "Required"},
    "nice_pl": {"pt": "Diferenciais", "en": "Nice-to-have"},
    "you_miss": {"pt": "Você ainda não cobre: {x}", "en": "You don't cover yet: {x}"},
    "you_miss_none": {"pt": "nada — candidate-se! 🚀", "en": "nothing — apply! 🚀"},
    "open_job": {"pt": "Abrir a vaga", "en": "Open posting"},
    "full_text": {"pt": "Texto completo", "en": "Full text"},
    "paste_job": {"pt": "Colar uma vaga (ex.: do LinkedIn ou InfoJobs)", "en": "Paste a posting (e.g. from LinkedIn)"},
    "link_opt": {"pt": "Link (opcional)", "en": "Link (optional)"},
    "job_text": {"pt": "Texto completo da vaga", "en": "Full posting text"},
    "add": {"pt": "Adicionar", "en": "Add"},
    "job_added": {"pt": "Vaga adicionada ({s}): {t}. Entra na análise na próxima atualização.",
                  "en": "Posting added ({s}): {t}. It joins the analysis on the next update."},

    # ---------------------------------------------------------------- roles
    "roles_title": {"pt": "Cargos", "en": "Roles"},
    "roles_sub": {"pt": "Ligue os cargos que quer acompanhar. Desligar só esconde as vagas dele: nada é apagado. Depois de ligar um cargo novo, atualize o mercado.",
                  "en": "Turn on the roles you want to follow. Turning one off only hides its postings: nothing is deleted. After turning on a new role, update the market."},
    "in_db": {"pt": "{n} vagas no banco", "en": "{n} postings stored"},
    "active": {"pt": "Ativo", "en": "On"},
    "what_they_do": {"pt": "O que esse profissional faz", "en": "What this role does"},
    "day_to_day": {"pt": "No dia a dia", "en": "Day to day"},
    "typical_skills": {"pt": "Skills típicas", "en": "Typical skills"},
    "searches_for": {"pt": "Busca por: {x}", "en": "Searches for: {x}"},
    "remove_custom": {"pt": "Remover este cargo personalizado", "en": "Remove this custom role"},
    "save_roles": {"pt": "Salvar cargos", "en": "Save roles"},
    "roles_none": {"pt": "Deixe pelo menos um cargo ativo.", "en": "Keep at least one role on."},
    "roles_saved": {"pt": "{n} cargos ativos · {m} vagas reclassificadas. Atualize o mercado para buscar vagas dos cargos novos.",
                    "en": "{n} roles on · {m} postings relabeled. Update the market to fetch postings for new roles."},
    "custom_role": {"pt": "Criar um cargo personalizado", "en": "Create a custom role"},
    "custom_role_help": {"pt": "Ex.: Prompt Engineer, Quant Analyst. O Waypoint procura vagas cujo título tenha essas palavras.",
                         "en": "E.g. Prompt Engineer, Quant Analyst. Waypoint looks for postings whose title has these words."},
    "role_name": {"pt": "Nome do cargo", "en": "Role name"},
    "add_role": {"pt": "Adicionar cargo", "en": "Add role"},
    "role_created": {"pt": "Cargo '{n}' criado e ativado. Atualize o mercado para buscar vagas.",
                     "en": "Role '{n}' created and turned on. Update the market to fetch postings."},
    "custom_summary": {"pt": "Cargo personalizado criado por você.", "en": "Custom role you created."},

    # ---------------------------------------------------------------- profile
    "profile_title": {"pt": "Meu perfil", "en": "My profile"},
    "resume": {"pt": "Currículo", "en": "Resume"},
    "resume_privacy": {"pt": "O arquivo fica em profile/ (fora do Git). Nome, e-mail, telefone, links e documentos são removidos antes de qualquer envio à IA.",
                       "en": "The file stays in profile/ (outside Git). Name, e-mail, phone, links and IDs are removed before anything goes to the AI."},
    "resume_file": {"pt": "Currículo (.pdf, .docx, .md, .txt)", "en": "Resume (.pdf, .docx, .md, .txt)"},
    "use_ai_levels": {"pt": "Usar IA para avaliar os níveis", "en": "Use AI to rate levels"},
    "current_profile": {"pt": "Perfil atual: {n} skills ({m}).", "en": "Current profile: {n} skills ({m})."},
    "read_resume": {"pt": "Ler currículo", "en": "Read resume"},
    "reading": {"pt": "Lendo o currículo…", "en": "Reading the resume…"},
    "skills_found": {"pt": "{n} skills encontradas ({m}).", "en": "{n} skills found ({m})."},
    "fit_gaps": {"pt": "Aderência e lacunas", "en": "Fit and gaps"},
    "compare_with": {"pt": "Comparar com", "en": "Compare with"},
    "all_roles_focus": {"pt": "Todos os cargos (seu nível-alvo)", "en": "All roles (your target level)"},
    "covered": {"pt": "Skills que você já cobre", "en": "Skills you already cover"},
    "gaps": {"pt": "Lacunas", "en": "Gaps"},
    "asked_in": {"pt": "Pedida em", "en": "Asked in"},
    "your_level": {"pt": "Seu nível", "en": "Your level"},
    "status": {"pt": "Status", "en": "Status"},
    "priority": {"pt": "Prioridade", "en": "Priority"},
    "est_hours": {"pt": "Horas estimadas", "en": "Estimated hours"},
    "your_levels": {"pt": "Seus níveis", "en": "Your levels"},
    "levels_help": {"pt": "Corrija o que a leitura errou. 0 = não tenho · 1 = já vi/estudei · 2 = usei em projeto ou trabalho · 3 = domino",
                    "en": "Fix what the reading got wrong. 0 = none · 1 = studied/seen · 2 = used in a project or job · 3 = strong"},
    "evidence": {"pt": "Evidência", "en": "Evidence"},
    "asked_by_market": {"pt": "(pedida pelo mercado)", "en": "(asked by the market)"},
    "save_levels": {"pt": "Salvar níveis", "en": "Save levels"},
    "levels_saved": {"pt": "Níveis salvos (profile/overrides.yaml, fora do Git).", "en": "Levels saved (profile/overrides.yaml, outside Git)."},
    "fit_by_role": {"pt": "Onde você está em cada cargo", "en": "Where you stand in each role"},
    "closest": {"pt": "Mais perto hoje: **{r}** ({v}).", "en": "Closest today: **{r}** ({v})."},
    "few_roles": {"pt": "Poucas vagas ainda (menos de {n}): {x}.", "en": "Few postings so far (fewer than {n}): {x}."},
    "send_cv_fit": {"pt": "Envie seu currículo para ver a aderência por cargo.", "en": "Upload your resume to see your fit per role."},

    # ---------------------------------------------------------------- report
    "report_title": {"pt": "Relatório e post", "en": "Report & post"},
    "post_draft": {"pt": "Rascunho com números reais do seu banco. Revise antes de publicar.",
                   "en": "Draft with real numbers from your database. Review before posting."},
    "post": {"pt": "Post", "en": "Post"},
    "public_report": {"pt": "Gerar relatório público (sem dados pessoais)", "en": "Build public report (no personal data)"},
    "private_report": {"pt": "Gerar relatório completo (privado)", "en": "Build full report (private)"},
    "saved_in": {"pt": "Salvo em {p}", "en": "Saved in {p}"},
    "numbers_json": {"pt": "Números (JSON)", "en": "Numbers (JSON)"},
}

WEEKDAYS = {"pt": ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"],
            "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
WEEKDAYS_SHORT = {"pt": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MONTHS = {"pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
                 "novembro", "dezembro"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"]}
SENIORITY = {"pt": {"intern": "Estágio", "junior": "Júnior", "mid": "Pleno", "senior": "Sênior", "staff_plus": "Staff+/Especialista"},
             "en": {"intern": "Intern", "junior": "Junior", "mid": "Mid-level", "senior": "Senior", "staff_plus": "Staff+"}}
REGION = {"pt": {"BR": "Brasil", "REMOTE_BR_OK": "Remoto (aceita Brasil)", "INTL": "Internacional"},
          "en": {"BR": "Brazil", "REMOTE_BR_OK": "Remote (open to Brazil)", "INTL": "International"}}


def set_lang(lang: str) -> None:
    LANG["lang"] = lang if lang in ("pt", "en") else "pt"


def lang() -> str:
    return LANG["lang"]


def t(key: str, **kw: Any) -> str:
    entry = S.get(key)
    if entry is None:
        return key
    s = entry.get(LANG["lang"]) or entry["pt"]
    return s.format(**kw) if kw else s


def hours(x: float) -> str:
    x = round(float(x) * 2) / 2
    s = f"{x:g}"
    return (s.replace(".", ",") if LANG["lang"] == "pt" else s) + "h"


def pct(x: float) -> str:
    return f"{x:.0%}"


def long_date(d: date) -> str:
    l = LANG["lang"]
    if l == "pt":
        return f"{WEEKDAYS[l][d.weekday()].capitalize()}, {d.day} de {MONTHS[l][d.month - 1]}"
    return f"{WEEKDAYS[l][d.weekday()]}, {MONTHS[l][d.month - 1]} {d.day}"


def short_date(d: date) -> str:
    l = LANG["lang"]
    return f"{d.day:02d}/{d.month:02d}" if l == "pt" else f"{MONTHS[l][d.month - 1][:3]} {d.day}"


def weekday_short(d: date) -> str:
    return WEEKDAYS_SHORT[LANG["lang"]][d.weekday()]


def seniority(k: str) -> str:
    return SENIORITY[LANG["lang"]].get(k, t("not_informed"))


def region(k: str) -> str:
    return REGION[LANG["lang"]].get(k, k)


def role_field(role: dict, name: str) -> Any:
    """Localized field of a role from the catalog (summary, description, day_to_day, typical_skills)."""
    if LANG["lang"] == "en" and role.get(f"{name}_en"):
        return role[f"{name}_en"]
    if role.get("custom") and name == "summary":
        return t("custom_summary")
    return role.get(name)
