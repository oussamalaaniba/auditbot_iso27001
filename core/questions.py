# core/questions.py
# Liste des questions types pour un audit ISO 27001
# Organisées par domaine de la norme ISO 27001:2022

ISO_QUESTIONS_INTERNE = {
    "A.5 Politiques de sécurité de l'information": [
        {"clause": "5.1", "question": "Existe-t-il une politique de sécurité formellement approuvée par la direction ?"},
        {"clause": "5.2", "question": "La politique est-elle communiquée à tous les employés et parties prenantes pertinentes ?"},
        {"clause": "5.3", "question": "Un processus de révision régulière de la politique est-il en place et documenté ?"}
    ],
    "A.6 Organisation de la sécurité de l'information": [
        {"clause": "6.1", "question": "Les rôles et responsabilités en matière de sécurité de l'information sont-ils clairement définis et communiqués ?"},
        {"clause": "6.2", "question": "Existe-t-il un responsable de la sécurité de l'information désigné (RSSI) ?"},
        {"clause": "6.3", "question": "La sécurité est-elle coordonnée entre les différents départements ?"}
    ],
    "A.7 Sécurité des ressources humaines": [
        {"clause": "7.1", "question": "Les candidats font-ils l’objet d’une vérification d’antécédents avant embauche ?"},
        {"clause": "7.2", "question": "Une formation à la sécurité est-elle dispensée à l’intégration ?"},
        {"clause": "7.3", "question": "Les obligations contractuelles incluent-elles des exigences de sécurité ?"}
    ],
    "A.8 Gestion des actifs": [
        {"clause": "8.1", "question": "Un inventaire des actifs est-il tenu à jour et approuvé ?"},
        {"clause": "8.2", "question": "Les actifs sont-ils classifiés selon leur sensibilité ?"},
        {"clause": "8.3", "question": "Des règles d'utilisation acceptable des actifs sont-elles définies ?"}
    ],
    "A.9 Contrôle d'accès": [
        {"clause": "9.1", "question": "Existe-t-il une politique de contrôle d’accès ?"},
        {"clause": "9.2", "question": "Les droits sont-ils accordés selon le principe du moindre privilège ?"},
        {"clause": "9.3", "question": "Les droits sont-ils révoqués immédiatement en cas de départ ou changement de poste ?"}
    ],
    "A.10 Cryptographie": [
        {"clause": "10.1", "question": "Une politique d’utilisation de la cryptographie est-elle définie ?"},
        {"clause": "10.2", "question": "Les clés cryptographiques sont-elles gérées de manière sécurisée ?"}
    ],
    "A.11 Sécurité physique et environnementale": [
        {"clause": "11.1", "question": "Les accès physiques aux zones sensibles sont-ils contrôlés ?"},
        {"clause": "11.2", "question": "Les équipements sont-ils protégés contre les menaces environnementales ?"},
        {"clause": "11.3", "question": "Une procédure de gestion des visiteurs est-elle appliquée ?"}
    ],
    "A.12 Sécurité opérationnelle": [
        {"clause": "12.1", "question": "Les procédures opérationnelles sont-elles documentées et accessibles ?"},
        {"clause": "12.2", "question": "Les changements sont-ils contrôlés par un processus de gestion des changements ?"},
        {"clause": "12.3", "question": "Les journaux d'activité sont-ils collectés et analysés régulièrement ?"}
    ],
    "A.13 Sécurité des communications": [
        {"clause": "13.1", "question": "Les réseaux sont-ils segmentés et protégés ?"},
        {"clause": "13.2", "question": "Les communications sensibles sont-elles chiffrées ?"},
        {"clause": "13.3", "question": "Une politique d'utilisation des services de messagerie est-elle définie ?"}
    ],
    "A.14 Acquisition, développement et maintenance des systèmes": [
        {"clause": "14.1", "question": "Les exigences de sécurité sont-elles intégrées dans les projets ?"},
        {"clause": "14.2", "question": "Des tests de sécurité sont-ils effectués avant mise en production ?"},
        {"clause": "14.3", "question": "Les vulnérabilités applicatives sont-elles corrigées rapidement ?"}
    ],
    "A.15 Relations avec les fournisseurs": [
        {"clause": "15.1", "question": "Les contrats fournisseurs incluent-ils des clauses de sécurité ?"},
        {"clause": "15.2", "question": "Les performances sécurité des fournisseurs sont-elles évaluées ?"}
    ],
    "A.16 Gestion des incidents de sécurité": [
        {"clause": "16.1", "question": "Un processus de gestion des incidents est-il défini ?"},
        {"clause": "16.2", "question": "Les incidents sont-ils documentés et analysés ?"},
        {"clause": "16.3", "question": "Les leçons apprises sont-elles intégrées aux procédures ?"}
    ],
    "A.17 Continuité d'activité": [
        {"clause": "17.1", "question": "La sécurité de l'information est-elle intégrée au PCA ?"},
        {"clause": "17.2", "question": "Le PCA est-il testé régulièrement ?"}
    ],
    "A.18 Conformité": [
        {"clause": "18.1", "question": "Les exigences légales et réglementaires sont-elles respectées ?"},
        {"clause": "18.2", "question": "Des audits internes sont-ils réalisés périodiquement ?"}
    ]
}

ISO_QUESTIONS_MANAGEMENT = {
    "4. Contexte de l'organisation": [
        {"clause": "4.1", "question": "Le contexte interne et externe de l'organisation est-il documenté ?"},
        {"clause": "4.2", "question": "Les besoins et attentes des parties prenantes sont-ils identifiés ?"},
        {"clause": "4.3", "question": "Le périmètre du SMSI est-il défini et documenté ?"}
    ],
    "5. Leadership": [
        {"clause": "5.1", "question": "La direction démontre-t-elle son engagement envers le SMSI ?"},
        {"clause": "5.2", "question": "Une politique de sécurité est-elle définie et approuvée par la direction ?"}
    ],
    "6. Planification": [
        {"clause": "6.1", "question": "Les risques liés à la sécurité de l'information sont-ils identifiés et évalués ?"},
        {"clause": "6.2", "question": "Des objectifs mesurables de sécurité sont-ils définis et suivis ?"}
    ],
    "7. Support": [
        {"clause": "7.1", "question": "Les ressources nécessaires au SMSI sont-elles allouées ?"},
        {"clause": "7.2", "question": "Le personnel est-il compétent et formé à la sécurité de l'information ?"}
    ],
    "8. Fonctionnement": [
        {"clause": "8.1", "question": "Les opérations sont-elles planifiées et maîtrisées ?"},
        {"clause": "8.2", "question": "Les résultats des évaluations des risques sont-ils intégrés aux activités ?"}
    ],
    "9. Évaluation des performances": [
        {"clause": "9.1", "question": "La performance du SMSI est-elle mesurée et évaluée ?"},
        {"clause": "9.2", "question": "Des audits internes sont-ils réalisés conformément au programme d'audit ?"}
    ],
    "10. Amélioration": [
        {"clause": "10.1", "question": "Les non-conformités sont-elles traitées par des actions correctives ?"},
        {"clause": "10.2", "question": "L'amélioration continue du SMSI est-elle démontrée ?"}
    ]
}

