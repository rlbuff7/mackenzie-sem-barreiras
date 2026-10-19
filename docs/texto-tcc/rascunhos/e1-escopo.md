# E1 — Escopo: problema, público-alvo e objetivos

> **RASCUNHO para revisão da equipe — gerado em 19/10/2026; nada aqui foi aprovado pela orientadora.**
>
> Marcações abertas: **[REF?]** citação nova a localizar; **[CONFERIR IBGE]** dado a conferir na fonte; **[DECIDIR COM A ORIENTADORA]** decisão que não é da equipe. Fonte do escopo: `CLAUDE.md` do escopo novo (14/10/2026) e cartões do Kanban no Notion (lidos em 19/10/2026).

Cartão do Kanban: E1 (prazo 20/10/2026; Equipe). Serve à reunião de ~27/10 e ao Projeto Parcial do TCC I.

## 1 Problema

O campus Higienópolis da Universidade Presbiteriana Mackenzie tem vias internas, praças, escadas, rampas e acessos entre prédios que não aparecem, com esse nível de detalhe, nos serviços de mapa de uso geral. Uma pessoa cega ou com baixa visão que não conhece o campus precisa saber onde está o caminho, onde há uma escada e qual é a entrada acessível de um prédio. Sem esse dado, essa informação precisa vir de outra fonte (a ser descrita com literatura, **[REF?]**).

O problema que o trabalho enfrenta é de **navegação e orientação espacial acessível** em área externa: dizer à pessoa, em voz, o que há ao redor e para onde seguir, sem fingir certeza quando a localização do celular está imprecisa. Uma orientação errada tem consequência física, o que torna a decisão de *quando calar* tão importante quanto a de *o que falar*.

Dimensão do público com deficiência visual no Brasil: **[CONFERIR IBGE]**. Os materiais do TCC I citam dois números diferentes (14,4 e 18,6 milhões de pessoas com deficiência), ambos atribuídos a "IBGE, 2022"; o repositório registra que provavelmente vêm de pesquisas distintas (Censo 2022 e PNAD Contínua 2022; ver `docs/decisoes-pendentes.md`, "Documentos acadêmicos"). Nenhum dos dois é usado aqui. O cartão "Corrigir o texto do TCC I" pede o número específico de pessoas com deficiência **visual**, a conferir na fonte.

Literatura de navegação assistiva e de orientação espacial para pessoas cegas, para sustentar a lacuna: **[REF?]**. O referencial de VGI usado no escopo antigo (Goodchild, 2007; Haklay, 2010; Liu et al., 2018; Miyata et al., 2021, 2025) saiu do referencial desta versão (CLAUDE.md §15).

## 2 Público-alvo

- **Prioritário:** pessoas com deficiência visual, cegas e com baixa visão.
- **Complementar:** estudantes, professores, funcionários e visitantes que não conhecem o campus.

Os dois públicos usam o mesmo sistema de duas formas complementares:

- **Visual:** mapa 2D do campus, seleção de destino e rota desenhada na tela;
- **Áudio:** orientações faladas durante o percurso, citando pontos de referência (por exemplo, "à sua direita há uma escada que dá acesso ao Prédio 31").

## 3 Objetivos

**Objetivo geral.** Desenvolver e avaliar um sistema web de navegação e orientação espacial acessível para as áreas externas do campus Higienópolis, com prioridade para pessoas com deficiência visual.

**Objetivos específicos** (propostos pela equipe; o texto final depende da decisão sobre a contribuição científica, abaixo):

1. Levantar os requisitos funcionais e não funcionais do sistema, com acessibilidade como requisito desde o primeiro componente (E2).
2. Medir em campo a precisão real do posicionamento por GPS do navegador no campus e compará-la com a precisão que o próprio navegador informa (`docs/medicao-gps.md`).
3. Mapear o recorte do campus como grafo pedonal (pontos de interesse, nós e arestas) em banco espacial (PostGIS) com roteamento por pgRouting (E4).
4. Calcular rotas até a **entrada** de um prédio, penalizando escadas e travessias conforme o perfil do usuário.
5. Projetar e implementar o módulo de orientação espacial: decidir o que falar, quando falar e como se comportar quando a localização está imprecisa.
6. Construir a interface web com mapa, escolha de destino por mapa e por busca textual, orientação falada e vibração complementar.
7. Avaliar o sistema com usuários (ou, no plano B, com especialistas em orientação e mobilidade) e apresentar os resultados.

**Contribuição científica.** Roteamento e síntese de voz são problemas resolvidos; integrá-los não é a contribuição. A hipótese de trabalho da equipe é que a contribuição está no módulo de orientação espacial (`backend/app/orientacao/`, ainda não criado; previsto no marco M4). Se ela está nesse módulo, na metodologia de avaliação ou em ambos: **[DECIDIR COM A ORIENTADORA]** (pendência #7 em `docs/decisoes-pendentes.md`).

## 4 Princípio de segurança

O sistema é **apoio à orientação**, nunca substituto de bengala, cão-guia ou das técnicas de mobilidade do usuário. Dele decorrem duas regras: *silêncio é melhor que palpite* (sem precisão suficiente, o sistema diz que não sabe e não arrisca uma direção) e *nenhuma orientação que empurre o usuário para a via, para uma escada não anunciada ou para um trecho não mapeado*. Esta frase precisa constar também na interface.

## 5 Recorte

- **Dentro:** apenas **caminhos e áreas externas** do campus Higienópolis, até a **entrada dos prédios**: vias internas, praças, caminhos e acessos entre prédios.
- O **destino** de uma rota é sempre a entrada de um prédio, nunca uma sala. Cada prédio tem um ou mais nós de entrada no grafo, com indicação de qual é acessível. A navegação termina com mensagem explícita de chegada.
- **Extensão do mapeamento no TCC I** (recorte do campus, não o campus todo): **[DECIDIR COM A ORIENTADORA]** (pendência #4). Nesta versão, a equipe mapeia primeiro um trecho pequeno para o protótipo e depois o recorte completo (ver E4).
- **Plataforma** (web mobile ou app nativo; a vibração não funciona no iOS pela web), **uso offline** e **precisão mínima para orientar** (provisório 15 m): **[DECIDIR COM A ORIENTADORA]** (pendências #1, #2 e #3). Enquanto isso, o código usa valores provisórios configuráveis.

## 6 O que fica fora

- **Interior dos prédios.** Nada de beacons BLE, Wi-Fi fingerprinting ou QR code indoor.
- **Entorno do campus** (ruas públicas e calçadas fora do campus): fora do recorte decidido em 14/10/2026.
- **Crowdsourcing de barreiras** (escopo anterior a 08/10/2026): pipeline de validação, tabelas `alertas`/`barreiras`, dados sintéticos e coleta colaborativa continuam no repositório, mas não são estendidos.
- **Serviços pagos** (Google Maps Platform): o projeto é de custo zero (tiles OpenStreetMap, pgRouting próprio, Web Speech API do navegador).
- **Substituir** bengala, cão-guia ou orientação e mobilidade profissional.

## 7 Para a equipe decidir ao revisar

- O objetivo geral fala em "sistema web"; isso depende da pendência #2.
- A lista de autores (o pôster e o artigo do TCC I têm dois, a divisão de trabalho tem três) precisa fechar antes do banner (cartão "Conferir a lista de autores do TCC II", 23/10).
