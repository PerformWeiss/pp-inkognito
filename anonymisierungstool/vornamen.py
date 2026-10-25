"""Kleine Liste häufiger Vornamen, nur um bei der Hauptperson zwischen "Bewerber" und "Bewerberin" zu wählen.

Unbekannte Namen bleiben offen ("Bewerber/in"); das Ergebnis lässt sich in der Prüfansicht jederzeit ändern."""
_F = """anna maria julia sabine petra claudia andrea stefanie nicole sandra christina katharina sarah laura lisa lena sophie sophia
johanna hannah emma mia emilia lea leonie marie anja birgit brigitte susanne monika ursula karin renate gabriele heike
silke nadine melanie jennifer jessica vanessa tanja kerstin simone angelika barbara christine elisabeth eva franziska
helena ines iris jana jasmin judith julia kathrin katja larissa linda lucia martina miriam nina olga oksana svetlana tatjana
natalia natalja irina elena yelena ekaterina galina ludmila lyudmila marina viktoria victoria valentina alina daria darya
kateryna iryna olena nataliia tetiana yulia yuliia anastasia anastasiya sofia sofiia mariia oleksandra
fatma ayse aylin elif zeynep merve emine hatice leyla selin ebru derya esra gül gamze
fatima aisha amina mariam layla noor sara sarah zahra yasmin leyla hanan
carolin caroline charlotte clara doris dorothea elke erika gudrun hanna helga ingrid jutta kristina maike manuela
margot marlene melissa michaela nathalie patricia rebecca regina rosa ruth sandy stella theresa ulrike vera verena wiebke
yvonne antje bettina cornelia daniela diana denise dagmar edith felicitas gisela hildegard iva jenny jessika kira"""
_M = """peter michael thomas andreas wolfgang klaus jürgen günter stefan christian markus martin frank bernd uwe jörg matthias
dirk holger ralf rainer manfred helmut hans karl heinz werner walter horst dieter gerhard jens sven tobias florian daniel
alexander sebastian patrick marco marcus mario oliver philipp philip felix lukas lucas leon luca maximilian max paul jan jonas
niklas nico nils tim timo tom fabian fabio benjamin johannes julian kevin lars marcel moritz robin simon steffen torsten
claas claus carsten karsten detlef ernst erwin franz fritz georg gregor harald heiko henrik hermann ingo jakob joachim
josef kai konrad kurt lothar ludwig norbert olaf otto rolf rüdiger siegfried theo ulrich volker wilhelm willi
andrei andrii oleksandr oleksii dmitri dmitrij dmytro sergej sergei serhii vladimir volodymyr viktor victor igor ivan
iwan maxim maksym mykola nikolai nikolaj pavel pawel taras yuri jurij juri artem anton bogdan denys roman oleg
mehmet mustafa ahmet ali hasan hüseyin ibrahim ismail murat emre can cem burak yusuf omar omer osman kemal
mohammed muhammad mohamed ahmad hassan hussein khalid karim tarek youssef amir reza hamid farid samir
david emil elias noah finn ben jonathan luis louis anton tobias raphael sascha dennis rene jörn arne bastian christoph
dominik fabrice gernot hendrik jannik jannis justus kilian lennart leo malte mathias mirko nick pascal ruben stephan
thorsten torben udo vincent yannick"""
FEMALE = set(_F.split())
MALE = set(_M.split()) - FEMALE
