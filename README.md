![](images/GAMMA_Logo.png)

# GAMMA V1 APP
## Game Automated Mechanics Modificatin & Adaptation

This repository, developed by Stefan Pietrusky, describes a prototype that is to be used as part of the EDUMING concept [[1]](https://arxiv.org/abs/2504.13878). Specifically, the aim is to simplify the development of digital learning games. With the help of GAMMA, specially configured learning mechanics in a game can be easily and quickly adapted to any content. Currently, GAMMA can be used to adapt a multiple choice mechanic [mc_mechanic.yymps]. The project will later provide specific game templates that already have mechanics of this type by default. 

The principle is demonstrated below as an example. As the mechanics have currently been developed for games with a basic resolution of 3840 x 2160, it must be adapted accordingly for your own tests in official GMS2 templates. The exact mode of operation is explained in a separate article that has not yet been published.

## Interface of the GAMMA app

![GAMMA V1 Interface (Gif by author)](images/GAMMAV1.gif)

In the current version, users have various options for generating questions on any topic. After one of the three variants (Ollama, OpenAI or Gemini) has been selected, the project directory of the template in which the learning mechanics were previously implemented is selected. The object that is overwritten in this example is oMC_Q. A topic and the difficulty of the questions are then defined and the GML code is generated. 

Alternatively, you can also upload your own .txt file in the appropriate format. In the IDE of GMS2, the code is replaced directly in the corresponding event of the object and the app can be started with new questions.

![GameMaker Studio 2 IDE with mc_mechanic example (Gif by author)](images/GMS2_IDE.gif)

The repository is being expanded step by step.

## Installing and running the application 
1. Clone this repository on your local computer: 
```bash 
git clone https://github.com/stefanpietrusky/gamma.git
```
2. Install the required dependencies:
```bash 
pip install -r requirements.txt
```
3. Install the IDE GameMaker Studio 2 [GMS2](https://gamemaker.io/de).
4. Install [Ollama](https://ollama.com/) and load the model [Llama3.2](https://ollama.com/library/llama3.2)
5. Install Google Gemini CLI as described [here](https://github.com/google-gemini/gemini-cli)
6. Get a Key for the OpenAI API [here](https://platform.openai.com/docs/overview)
7. Open a new project in GMS2 and install the learning mechanics [mc_mechanic.yymps] via "Tools" - "Import Local Package"
8. Start the app with:
```bash 
python app.py
```

## References
[1] Pietrusky, S. [2025]. Learning by gaming, coding and making with EDUMING: A new approach to utilising atypical digital games for learning. ARXIV CS.HC
