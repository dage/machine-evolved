#include "UIController.h"

void AUIController::BeginPlay()
{
	Super::BeginPlay();
	SetInputMode(FInputModeGameAndUI());
}
