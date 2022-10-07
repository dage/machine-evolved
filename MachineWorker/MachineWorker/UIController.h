#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "UIController.generated.h"

/**
 * 
 */
UCLASS()
class MACHINEWORKER_API AUIController : public APlayerController
{
	GENERATED_BODY()
	
public:
	virtual void BeginPlay() override;
};
