"""
Script para criar um executável do jogo Acampamento Defense.
Este script usa PyInstaller para empacotar o jogo em um único arquivo executável.
"""
import subprocess
import sys
import os

def check_pyinstaller():
    """Verifica se PyInstaller está instalado."""
    try:
        import PyInstaller
        print("[OK] PyInstaller encontrado")
        return True
    except ImportError:
        print("[X] PyInstaller nao encontrado")
        return False

def install_pyinstaller():
    """Instala PyInstaller."""
    print("\nInstalando PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("[OK] PyInstaller instalado com sucesso")

def build_executable():
    """Cria o executável usando PyInstaller."""
    print("\nCriando executável...")

    project_root = os.path.dirname(os.path.abspath(__file__))
    main_file = os.path.join(project_root, "acampamento_defense_pygamev8.py")

    # Nome do executável de saída
    exe_name = "AcampamentoDefense"

    # Comando PyInstaller usando o próprio Python atual
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",  # Criar um único arquivo executável
        "--windowed",  # Modo janela (sem console)
        "--name", exe_name,  # Nome do executável
        "--clean",  # Limpar cache antes de construir
        "--noconfirm",  # Não pedir confirmação para sobrescrever
        main_file
    ]

    print(f"Executando: {' '.join(command)}")

    try:
        subprocess.check_call(command)
        print(f"\n[OK] Executavel criado com sucesso!")
        print(f"  Localizacao: dist\\{exe_name}.exe")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Erro ao criar executavel: {e}")
        return False

def main():
    """Função principal do script de build."""
    print("=" * 60)
    print("Build do Executável - Acampamento Defense")
    print("=" * 60)

    project_root = os.path.dirname(os.path.abspath(__file__))
    main_file = os.path.join(project_root, "acampamento_defense_pygamev8.py")

    # Verificar se o arquivo principal existe
    if not os.path.exists(main_file):
        print("[X] Erro: arquivo acampamento_defense_pygamev8.py nao encontrado")
        print("  Execute este script na pasta do jogo")
        return False

    # Verificar e instalar PyInstaller se necessário
    if not check_pyinstaller():
        install_pyinstaller()

    # Criar executável
    success = build_executable()

    if success:
        print("\n" + "=" * 60)
        print("Build concluído com sucesso!")
        print("=" * 60)
        print("\nPara executar o jogo:")
        print("  .\\dist\\AcampamentoDefense.exe")
    else:
        print("\n" + "=" * 60)
        print("Build falhou")
        print("=" * 60)

    return success

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
