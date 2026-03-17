![](images/GAMMA_Logo.png)

# GAMMA V2 APP
## Game Automated Mechanics Modificatin & Adaptation

This repository, developed by Stefan Pietrusky, describes a prototype that is to be used as part of the EDUMING concept [[1]](https://arxiv.org/abs/2504.13878). GAMME combines project exploration code editing automated code summarization and AI driven support in one environment to make the modification and extension of GameMaker projects easier and more efficient.

The app is a Flask based tool that helps users inspect adapt and edit GameMaker projects through a browser interface. It lets the user enter a project folder path and then automatically scans the objects inside the project and builds a combined code summary of all object related files. After that the app displays the available object folders and their event files in a structured way so users can open individual events view their GML code and save changes directly from the interface. In addition to manual editing the app includes an AI supported project chat that uses an Ollama Cloud model to analyze the combined project code and suggest practical improvements for the selected GameMaker project. The model is guided by clear formatting rules so that its answers stay concise structured and focused on concrete code changes.

> **⚠️ Work in Progress:** This prototyp is currently under active development. While I make it available for research purposes, please be aware that there will be some changes to the functional structure. I recognize that some current technical design decisions may not be optimal and are subject to revision. Researchers using this prototyp should expect potential updates and changes. I recommend checking back regularly for updates and versioning information.

## Interface of the GAMMA app

![GAMMA V2 Interface (Gif by author)](images/GAMMAV2_1.gif)

The current version uses the Ollama Cloud model [qwen3.5:397b-cloud](https://ollama.com/library/qwen3.5:397b-cloud). Depending on your focus, you can swap out the model via the .env file.

The repository is being expanded step by step.

![GAMMA V2 Interface (Gif by author)](images/GAMMAV2_2.gif)

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
4. Create a [Ollama](https://ollama.com/) account and a API-Key to use cloud models
5. Update the value of `OLLAMA_CLOUD_API_KEY=` in the .env file according
6. Clone the repository for the first [EDUMING game template] (https://github.com/stefanpietrusky/EDUMING_GAME_1_ARENA_SHOOTER_TEMPLATE)
7. Start the app with:
```bash 
python app.py
```
8. Copy the template's path and paste it into GAMMA.

## References
[1] Pietrusky, S. [2025]. Learning by gaming, coding and making with EDUMING: A new approach to utilising atypical digital games for learning. ARXIV CS.HC
