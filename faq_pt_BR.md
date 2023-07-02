## Q1: erro ffmpeg/erro utf8.
Provavelmente não é um problema do FFmpeg, mas sim um problema de caminho de áudio;

O FFmpeg pode encontrar um erro ao ler caminhos contendo caracteres especiais como spaces e (), o que pode causar um erro FFmpeg; e quando o áudio do conjunto de treinamento contém caminhos chineses, gravá-lo em filelist.txt pode causar um erro utf8.<br>

## Q2:Não é possível encontrar o arquivo de índice após "Treinamento com um clique".
Se exibir "O treinamento está concluído. O programa é fechado ", então o modelo foi treinado com sucesso e os erros subsequentes são falsos;

A falta de um arquivo de índice 'adicionado' após o treinamento com um clique pode ser devido ao conjunto de treinamento ser muito grande, fazendo com que a adição do índice fique presa; isso foi resolvido usando o processamento em lote para adicionar o índice, o que resolve o problema de sobrecarga de memória ao adicionar o índice. Como solução temporária, tente clicar no botão "Train Index" novamente.<br>

## P3:Não é possível encontrar o modelo em “Inferindo o timbre” após o treinamento
Clique em "Atualizar lista de timbre" e verifique novamente; se ainda não estiver visível, verifique se há erros durante o treinamento e envie capturas de tela do console, da interface do usuário da Web e dos logs/experiment_name/*.log para os desenvolvedores para análise posterior.<br>

## P4:Como compartilhar um modelo/Como usar os modelos dos outros?
Os arquivos pth armazenados em rvc_root/logs/experiment_name não são destinados para compartilhamento ou inferência, mas para armazenar os checkpoits do experimento para reprodutibilidade e treinamento adicional. O modelo a ser compartilhado deve ser o arquivo pth de 60+MB na pasta pesos;

No futuro, pesos/exp_name.pth e logs/exp_name/added_xxx.index serão mesclados em um único arquivo de pesos/exp_name.zip para eliminar a necessidade de entrada manual de índice; portanto, compartilhe o arquivo zip, não o arquivo pth, a menos que você queira continuar treinando em uma máquina diferente;

Copiar/compartilhar os vários arquivos pth de centenas de MB da pasta de logs para a pasta de pesos para inferência forçada pode resultar em erros como falta de f0, tgt_sr ou outras chaves. Você precisa usar a guia ckpt na parte inferior para manualmente ou automaticamente (se as informações forem encontradas nos logs/EXP_NAME), selecione se deseja incluir informações de pitch e opções de taxa de amostragem de áudio de destino e, em seguida, extrair o modelo menor. Após a extração, haverá um arquivo pth de 60+ MB na pasta de pesos, e você pode atualizar as vozes para usá-lo.<br>

## Erro de conexão:
Você pode ter fechado o console (janela de linha de comando preta).<br>

## P6: Pop-up WebUI 'Valor esperado: linha 1 coluna 1 (caractere 0)'.
Desative o proxy LAN do sistema/proxy global e atualize.<br>

## P7:Como treinar e inferir sem a WebUI?
Script de treinamento:
<br>Você pode executar o treinamento em WebUI primeiro, e as versões de linha de comando do pré-processamento e treinamento do conjunto de dados serão exibidas na janela de mensagens.<br>

Script de inferência:
<br>https://huggingface.co/lj1995/VoiceConversionWebUI/blob/main/myinfer.py<br>


por exemplo<br>

runtime\python.exe myinfer.py 0 "E:\codes\py39\RVC-beta\todo-songs\1111.wav" "E:\codes\py39\logs\mi-test\added_IVF677_Flat_nprobe_7.index" harvest "test.wav" "weights/mi-test.pth" 0.6 cuda:0 Verdadeiro<br>


f0up_key=sys.argv[1
]<br>input_path=sys.argv[2
]<br>index_path=sys.argv[3
]<br>f0método=sys.argv[4]#colheita ou pm
<br>opt_path=sys.argv[5
]<br>model_path=sys.argv[6
]<br>index_rate=float(sys.argv[7])
<br>device=sys.argv[8
]<br>is_half=bool(sys.argv[9])<br>

## P8: Erro Cuda/Cuda fora da memória.
Há uma pequena chance de que haja um problema com a configuração do CUDA ou o dispositivo não seja suportado; mais provavelmente, não há memória suficiente (falta de memória).<br>

Para treinamento, reduza o tamanho do lote (se reduzir para 1 ainda não for suficiente, talvez seja necessário alterar a placa gráfica); para inferência, ajuste as configurações x_pad, x_query, x_center e x_max no arquivo config.py conforme necessário. Cartões de memória 4G ou inferiores (por exemplo, 1060(3G) e vários cartões 2G) podem ser abandonados, enquanto os cartões de memória 4G ainda têm uma chance.<br>

## Q9:Quantos total_epoch são ótimos?
Se a qualidade de áudio do conjunto de dados de treinamento for ruim e o nível de ruído for alto, 20-30 épocas são suficientes. Defini-lo muito alto não melhorará a qualidade de áudio do seu conjunto de treinamento de baixa qualidade.<br>

Se a qualidade de áudio do conjunto de treinamento for alta, o nível de ruído for baixo e houver duração suficiente, você poderá aumentá-lo. 200 é aceitável (uma vez que o treinamento é rápido e, se você puder preparar um conjunto de treinamento de alta qualidade, sua GPU provavelmente poderá lidar com uma duração de treinamento mais longa sem problemas).<br>

## Q10:Quanto tempo de treinamento é necessário?

Recomenda-se um conjunto de dados de cerca de 10 min a 50 min.<br>

Com garantia de alta qualidade de som e baixo ruído de fundo, mais pode ser adicionado se o timbre do conjunto de dados for uniforme.<br>

Para um conjunto de treinamento de alto nível (magra + tom distintivo), 5min a 10min é bom.<br>

Há algumas pessoas que treinaram com sucesso com dados de 1 a 2 minutos, mas o sucesso não é reproduzível por outros e não é muito informativo. <br>Isso requer que o conjunto de treinamento tenha um timbre muito distinto (por exemplo, um som de menina de anime arejado de alta frequência) e a qualidade do áudio seja alta;
Dados com menos de 1 minuto de duração não foram tentados com sucesso até o momento. |||UNTRANSLATED_CONTENT_START|||This is not recommended.<br>|||UNTRANSLATED_CONTENT_END|||


## Q11:Qual é a taxa do índice e como ajustá-la?
Se a qualidade do tom do modelo pré-treinado e da fonte de inferência for maior do que a do conjunto de treinamento, eles podem trazer a qualidade do tom do resultado da inferência, mas ao custo de um possível viés de tom em direção ao tom do modelo subjacente/fonte de inferência, em vez do tom do conjunto de treinamento, que é geralmente referido como "vazamento de tom".<br>

A taxa de índice é usada para reduzir/resolver o problema de vazamento de timbre. Se a taxa do índice for definida como 1, teoricamente não há vazamento de timbre da fonte de inferência e a qualidade do timbre é mais tendenciosa em relação ao conjunto de treinamento. Se o conjunto de treinamento tiver uma qualidade de som mais baixa do que a fonte de inferência, uma taxa de índice mais alta poderá reduzir a qualidade do som. Reduzi-lo a 0 não tem o efeito de usar a mistura de recuperação para proteger os tons definidos de treinamento.<br>

Se o conjunto de treinamento tiver boa qualidade de áudio e longa duração, aumente o total_epoch, quando o modelo em si é menos propenso a se referir à fonte inferida e ao modelo subjacente pré-treinado, e há pouco "vazamento de tom", o index_rate não é importante e você pode até não criar/compartilhar o arquivo de índice.<br>

## Q12:Como escolher o gpu ao inferir?
No arquivo config.py, selecione o número do cartão após "device cuda:".<br>

O mapeamento entre o número da placa e a placa gráfica pode ser visto na seção de informações da placa gráfica da guia de treinamento.<br>

## P13:Como usar o modelo salvo no meio do treinamento?
Salvar via extração de modelo na parte inferior da guia de processamento do ckpt.

## P14: Erro de arquivo/memória (durante o treinamento)?
Muitos processos e sua memória não é suficiente. Você pode corrigi-lo por:

1、diminuir a entrada no campo "Threads da CPU".

2 conjuntos、de trens pré-cortados para arquivos de áudio mais curtos.



